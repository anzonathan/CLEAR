'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getVideos, SharedVideo } from '@/lib/api';

export default function VideosPage() {
  const [videos, setVideos] = useState<SharedVideo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchVideos() {
      try {
        const data = await getVideos();
        setVideos(data);
      } catch (err) {
        console.error('Failed to fetch videos:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchVideos();
  }, []);

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString();
  };

  return (
    <div className="screen-pad with-tabs">
      <div className="topbar">
        <h3>Videos</h3>
        <Link href="/app/upload" className="icon-button">
          <svg className="icon" width="18" height="18" viewBox="0 0 24 24">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </Link>
      </div>

      {loading ? (
        <div className="loader" style={{ padding: '40px 0' }}>
          <i></i>
          <i></i>
          <i></i>
        </div>
      ) : videos.length === 0 ? (
        <div className="empty-state">
          <svg className="icon" width="48" height="48" viewBox="0 0 24 24" style={{ color: 'var(--muted)' }}>
            <polygon points="23 7 16 12 23 17 23 7" />
            <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          </svg>
          <h2>No Videos</h2>
          <p className="muted">Upload or record videos with your connections.</p>
          <Link href="/app/upload" className="btn btn-primary">
            Upload Video
          </Link>
        </div>
      ) : (
        <div className="video-grid">
          {videos.map((video) => (
            <Link
              key={video.id}
              href={`/app/videos/${video.id}`}
              className="video-card"
            >
              <div className="video-card-thumb">
                <svg className="icon" width="32" height="32" viewBox="0 0 24 24">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                <span className="video-duration">{formatDuration(video.duration_seconds)}</span>
              </div>
              <div className="video-card-info">
                <b>{video.file_name}</b>
                <span>
                  {video.uploader_name} · {formatDate(video.created_at)}
                </span>
                {video.processed ? (
                  <span className="pill light-pill" style={{ color: 'var(--primary)' }}>
                    ANALYZED
                  </span>
                ) : (
                  <span className="pill" style={{ background: 'var(--secondary)', color: 'var(--text)' }}>
                    PROCESSING
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
