type SignalingMessage = {
  type: string;
  sessionId?: string;
  userId?: string;
  peers?: string[];
  payload?: any;
};

type WebRTCEvents = {
  onRemoteStream: (stream: MediaStream) => void;
  onConnectionState: (state: RTCPeerConnectionState) => void;
  onError: (error: string) => void;
};

const ICE_SERVERS: RTCConfiguration = {
  iceServers: [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
  ],
};

export class WebRTCClient {
  private ws: WebSocket | null = null;
  private pc: RTCPeerConnection | null = null;
  private localStream: MediaStream | null = null;
  private sessionId: string;
  private userId: string;
  private events: WebRTCEvents;
  private remotePeerId: string | null = null;

  constructor(sessionId: string, userId: string, events: WebRTCEvents) {
    this.sessionId = sessionId;
    this.userId = userId;
    this.events = events;
  }

  async start(localStream: MediaStream) {
    this.localStream = localStream;

    // Connect to signaling server
    const wsUrl = (import.meta.env.VITE_WS_URL ?? "ws://localhost:3030") + "/ws/signaling";
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("Signaling connected");
      this.sendSignal({ type: "join", sessionId: this.sessionId, userId: this.userId });
    };

    this.ws.onmessage = (event) => {
      const message: SignalingMessage = JSON.parse(event.data);
      this.handleSignal(message);
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      this.events.onError("Connection error");
    };

    this.ws.onclose = () => {
      console.log("Signaling disconnected");
    };
  }

  private async handleSignal(message: SignalingMessage) {
    switch (message.type) {
      case "join":
        // We joined, check if there are existing peers
        if (message.peers && message.peers.length > 0) {
          // We're the second person, initiate call to first peer
          this.remotePeerId = message.peers[0];
          await this.createPeerConnection();
          await this.createOffer();
        }
        break;

      case "peer-joined":
        // New peer joined, they will initiate the call
        this.remotePeerId = message.userId!;
        await this.createPeerConnection();
        break;

      case "offer":
        // Received offer, create answer
        this.remotePeerId = message.userId!;
        if (!this.pc) {
          await this.createPeerConnection();
        }
        await this.handleOffer(message.payload);
        break;

      case "answer":
        // Received answer
        await this.handleAnswer(message.payload);
        break;

      case "ice-candidate":
        // Received ICE candidate
        await this.handleIceCandidate(message.payload);
        break;

      case "peer-left":
        // Peer disconnected
        this.cleanup();
        this.events.onError("Peer disconnected");
        break;

      case "error":
        this.events.onError(message.payload?.error || "Unknown error");
        break;
    }
  }

  private async createPeerConnection() {
    this.pc = new RTCPeerConnection(ICE_SERVERS);

    // Add local tracks
    if (this.localStream) {
      this.localStream.getTracks().forEach((track) => {
        this.pc!.addTrack(track, this.localStream!);
      });
    }

    // Handle remote stream
    this.pc.ontrack = (event) => {
      if (event.streams[0]) {
        this.events.onRemoteStream(event.streams[0]);
      }
    };

    // Handle ICE candidates
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.sendSignal({
          type: "ice-candidate",
          userId: this.remotePeerId!,
          payload: event.candidate.toJSON(),
        });
      }
    };

    // Handle connection state
    this.pc.onconnectionstatechange = () => {
      this.events.onConnectionState(this.pc!.connectionState);
    };
  }

  private async createOffer() {
    if (!this.pc) return;

    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    this.sendSignal({
      type: "offer",
      userId: this.remotePeerId!,
      payload: offer,
    });
  }

  private async handleOffer(offer: RTCSessionDescriptionInit) {
    if (!this.pc) return;

    await this.pc.setRemoteDescription(new RTCSessionDescription(offer));
    const answer = await this.pc.createAnswer();
    await this.pc.setLocalDescription(answer);

    this.sendSignal({
      type: "answer",
      userId: this.remotePeerId!,
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

  private sendSignal(message: SignalingMessage) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  toggleAudio(enabled: boolean) {
    if (this.localStream) {
      this.localStream.getAudioTracks().forEach((track) => {
        track.enabled = enabled;
      });
    }
  }

  toggleVideo(enabled: boolean) {
    if (this.localStream) {
      this.localStream.getVideoTracks().forEach((track) => {
        track.enabled = enabled;
      });
    }
  }

  stop() {
    this.sendSignal({ type: "leave" });
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
  }
}
