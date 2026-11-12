import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Icon, Text } from "../components/ui";
import { endLiveSession } from "../lib/api";
import { authClient } from "../lib/auth-client";
import { WebRTCClient } from "../lib/webrtc";

export default function LiveSessionScreen() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const { data: session } = authClient.useSession();

  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRef = useRef<HTMLVideoElement>(null);
  const webrtcRef = useRef<WebRTCClient | null>(null);

  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [connectionState, setConnectionState] = useState<string>("connecting");
  const [muted, setMuted] = useState(false);
  const [videoOff, setVideoOff] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId || !session?.user?.id) return;

    // Get local media
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then((stream) => {
        setLocalStream(stream);
        if (localVideoRef.current) {
          localVideoRef.current.srcObject = stream;
        }

        // Initialize WebRTC
        const webrtc = new WebRTCClient(sessionId, session.user.id, {
          onRemoteStream: (remoteStream) => {
            if (remoteVideoRef.current) {
              remoteVideoRef.current.srcObject = remoteStream;
            }
          },
          onConnectionState: (state) => {
            setConnectionState(state);
          },
          onError: (err) => {
            setError(err);
          },
        });

        webrtcRef.current = webrtc;
        webrtc.start(stream);
      })
      .catch((err) => {
        console.error("Failed to access camera:", err);
        setError("Camera access denied");
      });

    return () => {
      webrtcRef.current?.stop();
      localStream?.getTracks().forEach((track) => track.stop());
    };
  }, [sessionId, session?.user?.id]);

  // Timer
  useEffect(() => {
    if (connectionState !== "connected") return;
    const interval = setInterval(() => {
      setElapsed((e) => e + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [connectionState]);

  function toggleMute() {
    const newMuted = !muted;
    setMuted(newMuted);
    webrtcRef.current?.toggleAudio(!newMuted);
  }

  function toggleVideo() {
    const newVideoOff = !videoOff;
    setVideoOff(newVideoOff);
    webrtcRef.current?.toggleVideo(!newVideoOff);
  }

  async function handleEnd() {
    webrtcRef.current?.stop();
    localStream?.getTracks().forEach((track) => track.stop());

    if (sessionId) {
      await endLiveSession(sessionId);
    }
    navigate(-1);
  }

  function formatTime(seconds: number) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  const isConnected = connectionState === "connected";
  const isConnecting = connectionState === "connecting" || connectionState === "new";

  return (
    <div className="live-session-screen">
      <div className="live-session-header">
        {isConnected ? (
          <>
            <div className="live-indicator">
              <i />
              <span>LIVE</span>
            </div>
            <span className="live-timer">{formatTime(elapsed)}</span>
          </>
        ) : (
          <span className="live-timer">
            {error ? "Error" : "Connecting..."}
          </span>
        )}
      </div>

      <div className="live-videos">
        {/* Remote video (full screen) */}
        <div className="remote-video-container">
          {isConnected ? (
            <video
              ref={remoteVideoRef}
              autoPlay
              playsInline
              className="remote-video"
            />
          ) : (
            <div className="connecting-state">
              {error ? (
                <>
                  <Icon name="close" size={32} />
                  <Text as="p">{error}</Text>
                </>
              ) : (
                <>
                  <div className="loader">
                    <i />
                    <i />
                    <i />
                  </div>
                  <Text as="p">
                    {isConnecting
                      ? "Waiting for other player..."
                      : `Connection: ${connectionState}`}
                  </Text>
                </>
              )}
            </div>
          )}
        </div>

        {/* Local video (picture-in-picture) */}
        <div className="local-video-container">
          <video
            ref={localVideoRef}
            autoPlay
            playsInline
            muted
            className="local-video"
          />
          {videoOff && (
            <div className="video-off-overlay">
              <Icon name="video-off" size={24} />
            </div>
          )}
        </div>
      </div>

      <div className="live-controls">
        <button
          className={`control-button ${muted ? "active" : ""}`}
          onClick={toggleMute}
        >
          <Icon name={muted ? "mic-off" : "mic"} size={22} />
        </button>
        <button
          className={`control-button ${videoOff ? "active" : ""}`}
          onClick={toggleVideo}
        >
          <Icon name={videoOff ? "video-off" : "video"} size={22} />
        </button>
        <button className="control-button end-call" onClick={handleEnd}>
          <Icon name="phone" size={22} />
        </button>
      </div>
    </div>
  );
}
