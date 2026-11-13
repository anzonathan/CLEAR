/**
 * WebRTC client for live video sessions
 */

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export interface SignalingMessage {
  type: 'join' | 'offer' | 'answer' | 'ice-candidate' | 'leave' | 'error' | 'peer-joined' | 'peer-left';
  sessionId?: string;
  userId?: string;
  peers?: string[];
  payload?: unknown;
}

export class WebRTCClient {
  private ws: WebSocket | null = null;
  private pc: RTCPeerConnection | null = null;
  private sessionId: string;
  private userId: string;
  private localStream: MediaStream | null = null;
  private remoteStream: MediaStream | null = null;

  private onRemoteStream: ((stream: MediaStream) => void) | null = null;
  private onConnectionStateChange: ((state: RTCPeerConnectionState) => void) | null = null;
  private onError: ((error: string) => void) | null = null;

  constructor(sessionId: string, userId: string) {
    this.sessionId = sessionId;
    this.userId = userId;
  }

  setOnRemoteStream(callback: (stream: MediaStream) => void) {
    this.onRemoteStream = callback;
  }

  setOnConnectionStateChange(callback: (state: RTCPeerConnectionState) => void) {
    this.onConnectionStateChange = callback;
  }

  setOnError(callback: (error: string) => void) {
    this.onError = callback;
  }

  async connect(localStream: MediaStream): Promise<void> {
    this.localStream = localStream;

    // Connect to signaling server
    this.ws = new WebSocket(`${WS_URL}/ws/signaling/`);

    this.ws.onopen = () => {
      this.send({
        type: 'join',
        sessionId: this.sessionId,
        userId: this.userId,
      });
    };

    this.ws.onmessage = (event) => {
      const message: SignalingMessage = JSON.parse(event.data);
      this.handleSignalingMessage(message);
    };

    this.ws.onerror = () => {
      this.onError?.('WebSocket connection failed');
    };

    this.ws.onclose = () => {
      this.cleanup();
    };
  }

  private async handleSignalingMessage(message: SignalingMessage) {
    switch (message.type) {
      case 'join':
        // Connected to room, create offer if there are peers
        if (message.peers && message.peers.length > 0) {
          await this.createPeerConnection();
          await this.createOffer(message.peers[0]);
        }
        break;

      case 'peer-joined':
        // New peer joined, create offer
        if (message.userId) {
          await this.createPeerConnection();
          await this.createOffer(message.userId);
        }
        break;

      case 'offer':
        // Received offer, create answer
        if (message.userId && message.payload) {
          await this.handleOffer(message.userId, message.payload as RTCSessionDescriptionInit);
        }
        break;

      case 'answer':
        // Received answer
        if (message.payload) {
          await this.handleAnswer(message.payload as RTCSessionDescriptionInit);
        }
        break;

      case 'ice-candidate':
        // Received ICE candidate
        if (message.payload) {
          await this.handleIceCandidate(message.payload as RTCIceCandidateInit);
        }
        break;

      case 'peer-left':
        // Peer left, cleanup
        this.cleanup();
        break;

      case 'error':
        this.onError?.((message.payload as { error: string })?.error || 'Unknown error');
        break;
    }
  }

  private async createPeerConnection() {
    this.pc = new RTCPeerConnection({
      iceServers: [
        { urls: 'stun:stun.l.google.com:19302' },
        { urls: 'stun:stun1.l.google.com:19302' },
      ],
    });

    // Add local tracks
    if (this.localStream) {
      this.localStream.getTracks().forEach((track) => {
        this.pc?.addTrack(track, this.localStream!);
      });
    }

    // Handle remote tracks
    this.pc.ontrack = (event) => {
      if (!this.remoteStream) {
        this.remoteStream = new MediaStream();
      }
      event.streams[0].getTracks().forEach((track) => {
        this.remoteStream?.addTrack(track);
      });
      this.onRemoteStream?.(this.remoteStream);
    };

    // Handle ICE candidates
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.send({
          type: 'ice-candidate',
          payload: event.candidate.toJSON(),
        });
      }
    };

    // Handle connection state changes
    this.pc.onconnectionstatechange = () => {
      if (this.pc) {
        this.onConnectionStateChange?.(this.pc.connectionState);
      }
    };
  }

  private async createOffer(targetUserId: string) {
    if (!this.pc) return;

    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    this.send({
      type: 'offer',
      userId: targetUserId,
      payload: offer,
    });
  }

  private async handleOffer(fromUserId: string, offer: RTCSessionDescriptionInit) {
    await this.createPeerConnection();
    if (!this.pc) return;

    await this.pc.setRemoteDescription(new RTCSessionDescription(offer));

    const answer = await this.pc.createAnswer();
    await this.pc.setLocalDescription(answer);

    this.send({
      type: 'answer',
      userId: fromUserId,
      payload: answer,
    });
  }

  private async handleAnswer(answer: RTCSessionDescriptionInit) {
    if (!this.pc) return;
    await this.pc.setRemoteDescription(new RTCSessionDescription(answer));
  }

  private async handleIceCandidate(candidate: RTCIceCandidateInit) {
    if (!this.pc) return;
    await this.pc.addIceCandidate(new RTCIceCandidate(candidate));
  }

  private send(message: SignalingMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  disconnect() {
    this.send({ type: 'leave' });
    this.cleanup();
  }

  private cleanup() {
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.remoteStream = null;
  }

  getLocalStream(): MediaStream | null {
    return this.localStream;
  }

  getRemoteStream(): MediaStream | null {
    return this.remoteStream;
  }
}
