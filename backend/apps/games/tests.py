"""Tests for game invites: the partner has to accept a game before it can start."""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.connections.models import Connection

from .models import Game


class GameInviteTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(email='alice@example.com', password='x')
        self.bob = User.objects.create_user(email='bob@example.com', password='x')
        self.connection = Connection.objects.create(user_a=self.alice, user_b=self.bob)

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def invite(self, by=None):
        when = (timezone.now() + timedelta(hours=1)).isoformat()
        res = self.client_for(by or self.alice).post(
            '/api/games/', {'connection_id': self.connection.id, 'scheduled_at': when}, format='json'
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def test_new_game_is_pending_and_awaits_partner(self):
        data = self.invite()
        self.assertEqual(data['status'], 'pending')
        self.assertFalse(data['awaiting_me'])
        self.assertEqual(data['proposed_by']['email'], 'alice@example.com')
        bob_view = self.client_for(self.bob).get(f"/api/games/{data['id']}/").data
        self.assertTrue(bob_view['awaiting_me'])

    def test_partner_accepts(self):
        gid = self.invite()['id']
        res = self.client_for(self.bob).post(f'/api/games/{gid}/accept/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['status'], 'scheduled')
        self.assertFalse(res.data['awaiting_me'])

    def test_proposer_cannot_accept_own_invite(self):
        gid = self.invite()['id']
        res = self.client_for(self.alice).post(f'/api/games/{gid}/accept/')
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Game.objects.get(id=gid).status, 'pending')

    def test_partner_declines(self):
        gid = self.invite()['id']
        res = self.client_for(self.bob).post(f'/api/games/{gid}/decline/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['status'], 'declined')
        # A declined invite cannot then be accepted.
        res = self.client_for(self.bob).post(f'/api/games/{gid}/accept/')
        self.assertEqual(res.status_code, 409)

    def test_proposer_can_withdraw_invite(self):
        gid = self.invite()['id']
        res = self.client_for(self.alice).delete(f'/api/games/{gid}/')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['status'], 'cancelled')

    def test_pending_game_cannot_start(self):
        gid = self.invite()['id']
        Game.objects.filter(id=gid).update(camera_a_id='cam1', camera_b_id='cam2')
        with mock.patch('apps.games.services.require_manager') as manager:
            res = self.client_for(self.alice).post(f'/api/games/{gid}/start/')
        self.assertEqual(res.status_code, 409)
        manager.assert_not_called()

    def test_reschedule_needs_fresh_acceptance_from_other_player(self):
        gid = self.invite()['id']
        self.client_for(self.bob).post(f'/api/games/{gid}/accept/')
        later = (timezone.now() + timedelta(days=1)).isoformat()
        res = self.client_for(self.bob).patch(f'/api/games/{gid}/', {'scheduled_at': later}, format='json')
        self.assertEqual(res.data['status'], 'pending')
        self.assertEqual(res.data['proposed_by']['email'], 'bob@example.com')
        res = self.client_for(self.alice).post(f'/api/games/{gid}/accept/')
        self.assertEqual(res.data['status'], 'scheduled')

    def test_title_change_keeps_acceptance(self):
        gid = self.invite()['id']
        self.client_for(self.bob).post(f'/api/games/{gid}/accept/')
        res = self.client_for(self.alice).patch(f'/api/games/{gid}/', {'title': 'Friendly'}, format='json')
        self.assertEqual(res.data['status'], 'scheduled')
