"""Tests for recording playback, segments and data export (no camera hardware needed)."""

import io
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock, skipUnless

import numpy as np
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase
from rest_framework.test import APIClient

from . import media, services
from .models import Game


def _write_mp4v(path: Path, frames=30, size=(320, 180), fps=30.0):
    import cv2

    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), fps, size)
    for i in range(frames):
        img = np.full((size[1], size[0], 3), (i * 8) % 255, dtype=np.uint8)
        w.write(img)
    w.release()


class SegmentValidationTests(SimpleTestCase):
    def test_clean_segments_normalises(self):
        out = services.clean_segments([
            {'id': 'a1', 'end': 'end_a', 'start_s': '1.23456', 'end_s': 4, 'label': '  Rally 1 '},
            {'id': 'b2', 'end': 'end_b', 'start_s': 0, 'end_s': 2.5},
        ])
        self.assertEqual(out[0], {'id': 'a1', 'end': 'end_a', 'label': 'Rally 1', 'start_s': 1.235, 'end_s': 4.0})
        self.assertEqual(out[1]['label'], 'Segment 2')

    def test_clean_segments_rejects_bad_input(self):
        bad = [
            'nope',
            [{'id': 'x', 'end': 'end_c', 'start_s': 0, 'end_s': 1}],
            [{'id': 'x', 'end': 'end_a', 'start_s': 2, 'end_s': 1}],
            [{'id': 'x', 'end': 'end_a', 'start_s': -1, 'end_s': 1}],
            [{'id': 'bad id!', 'end': 'end_a', 'start_s': 0, 'end_s': 1}],
            [{'id': 'x', 'end': 'end_a', 'start_s': 0, 'end_s': 1}] * 2,
        ]
        for raw in bad:
            with self.assertRaises(services.GameError, msg=raw):
                services.clean_segments(raw)


class RangedResponseTests(SimpleTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'v.mp4'
        self.path.write_bytes(bytes(range(256)) * 4)  # 1024 bytes
        self.rf = RequestFactory()

    def tearDown(self):
        self.tmp.cleanup()

    def _body(self, resp):
        return b''.join(resp.streaming_content)

    def test_full_file(self):
        resp = media.ranged_file_response(self.rf.get('/'), self.path)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Accept-Ranges'], 'bytes')
        self.assertEqual(len(self._body(resp)), 1024)

    def test_byte_range(self):
        resp = media.ranged_file_response(self.rf.get('/', HTTP_RANGE='bytes=10-19'), self.path)
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp['Content-Range'], 'bytes 10-19/1024')
        self.assertEqual(self._body(resp), bytes(range(10, 20)))

    def test_open_ended_and_suffix(self):
        resp = media.ranged_file_response(self.rf.get('/', HTTP_RANGE='bytes=1000-'), self.path)
        self.assertEqual(len(self._body(resp)), 24)
        resp = media.ranged_file_response(self.rf.get('/', HTTP_RANGE='bytes=-4'), self.path)
        self.assertEqual(resp['Content-Range'], 'bytes 1020-1023/1024')

    def test_unsatisfiable(self):
        resp = media.ranged_file_response(self.rf.get('/', HTTP_RANGE='bytes=5000-'), self.path)
        self.assertEqual(resp.status_code, 416)


@skipUnless(media.ffmpeg_bin(), 'ffmpeg not available')
class ConversionTests(SimpleTestCase):
    def test_prepare_converts_to_h264_once(self):
        import cv2

        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'cam_raw.mp4'
            _write_mp4v(src, frames=45)
            self.assertEqual(media.prepare(src)['state'], 'converting')
            for _ in range(200):
                state = media.prepare(src)
                if state['state'] != 'converting':
                    break
                time.sleep(0.1)
            self.assertEqual(state, {'state': 'ready'})
            web = media.web_path(src)
            cap = cv2.VideoCapture(str(web))
            fourcc = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, 'little').decode()
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            self.assertIn(fourcc.lower(), ('avc1', 'h264'))
            self.assertEqual(frames, 45)  # frame-accurate: browser frame N == pipeline frame N


class DevGameApiTests(TestCase):
    def setUp(self):
        from apps.connections.models import Connection

        User = get_user_model()
        self.dev = User.objects.create_user(email='dev@example.com', password='x', name='Dev', role='developer')
        a = User.objects.create_user(email='a@example.com', password='x', name='A')
        b = User.objects.create_user(email='b@example.com', password='x', name='B')
        conn = Connection.objects.create(user_a=a, user_b=b)
        self.game = Game.objects.create(
            connection=conn, created_by=a, scheduled_at='2026-01-01T10:00Z', status='completed',
            camera_a_id='camA', camera_b_id='camB', recording_id='rec1',
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        rec = self.data_dir / 'recordings' / 'rec1'
        rec.mkdir(parents=True)
        _write_mp4v(rec / 'camA_raw.mp4', frames=60)
        self.manager = SimpleNamespace(
            data_dir=str(self.data_dir),
            get_recording=lambda rid: {'cameras': [{'camera_id': 'camA', 'files': [{'filename': 'camA_raw.mp4'}]}]},
            registry=SimpleNamespace(calibration_path=lambda cid: None),
            get_camera=lambda cid: None,
        )
        patches = [
            mock.patch('apps.games.services.get_field_manager', return_value=self.manager),
            mock.patch('apps.games.views.get_field_manager', return_value=self.manager),
            mock.patch('apps.field.views.get_field_manager', return_value=self.manager),
            # Run analysis synchronously so the test sees the result.
            mock.patch('apps.games.services.threading.Thread', new=lambda target, args, daemon: SimpleNamespace(start=lambda: target(*args))),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = APIClient()
        self.client.force_authenticate(self.dev)

    def tearDown(self):
        self.tmp.cleanup()

    def url(self, suffix=''):
        return f'/api/dev/games/{self.game.id}/{suffix}'

    def test_segments_analyse_and_export(self):
        segs = [
            {'id': 'r1', 'end': 'end_a', 'label': 'Rally 1', 'start_s': 0.5, 'end_s': 1.0},
            {'id': 'r2', 'end': 'end_a', 'label': 'Rally 2', 'start_s': 1.0, 'end_s': 1.9},
        ]
        resp = self.client.put(self.url('segments/'), {'segments': segs}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual([s['id'] for s in resp.json()['segments']], ['r1', 'r2'])
        self.assertEqual(resp.json()['videos']['end_a'], {'raw': True, 'annotated': False})

        resp = self.client.post(self.url('analyze/'), {'segment_ids': ['r1', 'r2']}, format='json')
        self.assertEqual(resp.status_code, 202, resp.content)
        self.game.refresh_from_db()
        self.assertEqual(self.game.analysis_status, 'done', self.game.analysis)
        r1 = self.game.analysis['segments']['r1']
        self.assertEqual(r1['segment']['start_frame'], 15)  # 0.5 s * 30 fps
        self.assertEqual(r1['segment']['end_frame'], 30)
        self.assertEqual(r1['total_frames'], 15)

        resp = self.client.get(self.url('export/') + '?segments=r2')
        self.assertEqual(resp.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        names = set(z.namelist())
        self.assertIn('manifest.json', names)
        self.assertIn('runs.csv', names)
        self.assertIn('end_a_r2/tracks.csv', names)
        self.assertNotIn('end_a_r1/tracks.csv', names)
        tracks = z.read('end_a_r2/tracks.csv').decode().splitlines()
        self.assertEqual(len(tracks) - 1, 27)  # frames 30..56
        self.assertTrue(tracks[1].startswith('30,'))

        # Removing a segment forgets its analysis.
        resp = self.client.put(self.url('segments/'), {'segments': segs[1:]}, format='json')
        self.game.refresh_from_db()
        self.assertEqual(list(self.game.analysis['segments']), ['r2'])

    def test_analyse_unknown_segment_is_rejected(self):
        resp = self.client.post(self.url('analyze/'), {'segment_ids': ['nope']}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_video_requires_prepare_then_streams(self):
        resp = self.client.get(self.url('video/end_a/'))
        self.assertEqual(resp.status_code, 409)
        resp = self.client.get(self.url('video/end_b/'))
        self.assertEqual(resp.status_code, 404)
        web = media.web_path(self.data_dir / 'recordings' / 'rec1' / 'camA_raw.mp4')
        web.write_bytes(b'0123456789')
        resp = self.client.get(self.url('video/end_a/'), HTTP_RANGE='bytes=2-5')
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(b''.join(resp.streaming_content), b'2345')

    def test_export_with_nothing_analysed(self):
        resp = self.client.get(self.url('export/'))
        self.assertEqual(resp.status_code, 400)


class DevStartGameTests(TestCase):
    """Developers can start a scheduled game only when both players' phones are online."""

    def setUp(self):
        from apps.connections.models import Connection

        User = get_user_model()
        self.dev = User.objects.create_user(email='dev@example.com', password='x', name='Dev', role='developer')
        self.a = User.objects.create_user(email='a@example.com', password='x', name='Ana')
        self.b = User.objects.create_user(email='b@example.com', password='x', name='Ben')
        conn = Connection.objects.create(user_a=self.a, user_b=self.b)
        self.game = Game.objects.create(
            connection=conn, created_by=self.a, scheduled_at='2026-01-01T10:00Z', status='scheduled',
            camera_a_id='camA', camera_a_user=self.a, camera_b_id='camB', camera_b_user=self.b,
        )
        self.online = {'camA': True, 'camB': False}
        self.started = []
        self.manager = SimpleNamespace(
            get_camera=lambda cid: {'online': self.online.get(cid, False), 'active': True},
            in_preview=lambda cid: False,
            match_preview=False,
            match_id='m1',
            start_match=lambda a, b, preview=False: self.started.append((a, b)),
            start_recording=lambda cams, name='': {'id': 'rec9'},
        )
        for target in ('apps.games.services.get_field_manager', 'apps.field.views.get_field_manager'):
            p = mock.patch(target, return_value=self.manager)
            p.start()
            self.addCleanup(p.stop)
        self.client = APIClient()
        self.client.force_authenticate(self.dev)
        self.url = f'/api/dev/games/{self.game.id}/start/'

    def test_blocked_while_a_phone_is_offline(self):
        detail = self.client.get(f'/api/dev/games/{self.game.id}/').json()
        self.assertEqual(detail['start_blockers'], ["Ben's phone (End B) is offline."])
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 409)
        self.assertIn("Ben's phone (End B) is offline.", resp.json()['error'])
        self.game.refresh_from_db()
        self.assertEqual(self.game.status, 'scheduled')
        self.assertEqual(self.started, [])

    def test_missing_player_is_reported(self):
        Game.objects.filter(pk=self.game.pk).update(camera_b_id='', camera_b_user=None)
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 409)
        self.assertIn('No player has taken End B yet.', resp.json()['error'])

    def test_starts_when_both_online(self):
        self.online['camB'] = True
        detail = self.client.get(f'/api/dev/games/{self.game.id}/').json()
        self.assertEqual(detail['start_blockers'], [])
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['status'], 'live')
        self.assertIsNone(resp.json()['start_blockers'])
        self.assertEqual(self.started, [('camA', 'camB')])
        self.game.refresh_from_db()
        self.assertEqual((self.game.status, self.game.recording_id, self.game.match_id), ('live', 'rec9', 'm1'))

    def test_players_cannot_use_dev_start(self):
        self.online['camB'] = True
        player = APIClient()
        player.force_authenticate(self.a)
        self.assertEqual(player.post(self.url).status_code, 403)


class FakeManager:
    """Just enough of the field manager to model one match and one recording at a time."""

    def __init__(self):
        self.recording = None
        self.match_id = None
        self.match_preview = False
        self.n = 0
        self.matches = []
        self.registry = SimpleNamespace(get=lambda cid: {'token': f'tok-{cid}'})

    def get_camera(self, cid):
        return {'online': True, 'active': True}

    def in_preview(self, cid):
        return False

    def start_match(self, a, b, preview=False):
        self.n += 1
        self.match_id = f'm{self.n}'
        self.matches.append((a, b))

    def stop_match(self):
        self.match_id = None

    def start_recording(self, cams, name=''):
        if self.recording is not None:
            raise ValueError('A recording is already in progress.')
        self.n += 1
        self.recording = SimpleNamespace(id=f'rec{self.n}', paused=False)
        return {'id': self.recording.id}

    def pause_recording(self):
        self.recording.paused = True

    def resume_recording(self):
        self.recording.paused = False

    def stop_recording(self):
        self.recording = None


class DevRecordingTests(TestCase):
    def setUp(self):
        from apps.connections.models import Connection

        User = get_user_model()
        self.dev = User.objects.create_user(email='dev@example.com', password='x', name='Dev', role='developer')
        self.a = User.objects.create_user(email='a@example.com', password='x', name='Ana')
        self.b = User.objects.create_user(email='b@example.com', password='x', name='Ben')
        self.conn = Connection.objects.create(user_a=self.a, user_b=self.b)
        self.manager = FakeManager()
        for target in ('apps.games.services.get_field_manager', 'apps.field.views.get_field_manager'):
            p = mock.patch(target, return_value=self.manager)
            p.start()
            self.addCleanup(p.stop)
        self.dev_client = APIClient()
        self.dev_client.force_authenticate(self.dev)
        self.player = APIClient()
        self.player.force_authenticate(self.a)

    def make_game(self, dev_mode, title='Session'):
        return Game.objects.create(
            connection=self.conn, created_by=self.a, scheduled_at='2026-01-01T10:00Z', status='scheduled',
            title=title, dev_mode=dev_mode,
            camera_a_id='camA', camera_a_user=self.a, camera_b_id='camB', camera_b_user=self.b,
        )

    def record(self, game, action):
        return self.dev_client.post(f'/api/dev/games/{game.id}/record/', {'action': action}, format='json')

    def test_players_can_schedule_a_dev_mode_game(self):
        resp = self.player.post('/api/games/', {
            'connection_id': self.conn.id, 'scheduled_at': '2099-01-01T10:00Z', 'dev_mode': True,
        }, format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertTrue(resp.json()['dev_mode'])
        self.assertTrue(Game.objects.get(id=resp.json()['id']).dev_mode)

    def test_dev_mode_game_goes_live_without_recording_then_dev_controls_it(self):
        game = self.make_game(dev_mode=True)
        resp = self.player.post(f'/api/games/{game.id}/start/')  # phones auto-start as usual
        self.assertEqual(resp.json()['status'], 'live')
        self.assertEqual(resp.json()['recording_state'], 'off')
        self.assertIsNone(self.manager.recording)

        self.assertEqual(self.record(game, 'pause').status_code, 400)
        resp = self.record(game, 'start')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()['recording_state'], 'recording')
        self.assertEqual(self.record(game, 'start').status_code, 400)

        self.assertEqual(self.record(game, 'pause').json()['recording_state'], 'paused')
        self.assertTrue(self.manager.recording.paused)
        self.assertEqual(self.player.get(f'/api/games/{game.id}/').json()['recording_state'], 'paused')
        self.assertEqual(self.record(game, 'resume').json()['recording_state'], 'recording')
        self.assertEqual(self.record(game, 'bogus').status_code, 400)

    def test_normal_game_still_records_on_start(self):
        game = self.make_game(dev_mode=False)
        self.player.post(f'/api/games/{game.id}/start/')
        game.refresh_from_db()
        self.assertTrue(game.recording_id)
        self.assertEqual(self.record(game, 'pause').json()['recording_state'], 'paused')

    def test_next_game_closes_recording_and_starts_new_game_on_same_cameras(self):
        game = self.make_game(dev_mode=True, title='Session')
        self.player.post(f'/api/games/{game.id}/start/')
        self.record(game, 'start')
        first_rec = Game.objects.get(pk=game.pk).recording_id

        resp = self.dev_client.post(f'/api/dev/games/{game.id}/next/')
        self.assertEqual(resp.status_code, 201, resp.content)
        nxt = resp.json()
        self.assertEqual((nxt['status'], nxt['title'], nxt['recording_state']), ('live', 'Session #2', 'off'))
        self.assertTrue(nxt['dev_mode'])

        game.refresh_from_db()
        self.assertEqual(game.status, 'completed')
        self.assertEqual(game.recording_id, first_rec)
        self.assertEqual(game.next_game_id, nxt['id'])
        self.assertIsNone(self.manager.recording)  # first recording was closed
        self.assertEqual(self.manager.matches, [('camA', 'camB'), ('camA', 'camB')])

        # Phones on the old page learn where to go; their camera token is unchanged.
        old_view = self.player.get(f'/api/games/{game.id}/').json()
        self.assertEqual(old_view['next_game_id'], nxt['id'])
        new_view = self.player.get(f'/api/games/{nxt["id"]}/').json()
        self.assertEqual(new_view['my_camera']['id'], old_view['my_camera']['id'])

        # The next game records independently into its own file.
        self.assertEqual(self.record(Game.objects.get(id=nxt['id']), 'start').json()['recording_state'], 'recording')
        third = self.dev_client.post(f'/api/dev/games/{nxt["id"]}/next/').json()
        self.assertEqual(third['title'], 'Session #3')

    def test_cameras_cannot_be_released_after_the_game(self):
        game = self.make_game(dev_mode=True)
        self.player.post(f'/api/games/{game.id}/start/')
        self.dev_client.post(f'/api/dev/games/{game.id}/next/')
        resp = self.player.delete(f'/api/games/{game.id}/camera/')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Game.objects.get(pk=game.pk).camera_a_id, 'camA')

    def test_players_cannot_control_recording(self):
        game = self.make_game(dev_mode=True)
        self.player.post(f'/api/games/{game.id}/start/')
        self.assertEqual(self.player.post(f'/api/dev/games/{game.id}/record/', {'action': 'start'}, format='json').status_code, 403)
        self.assertEqual(self.player.post(f'/api/dev/games/{game.id}/next/').status_code, 403)
