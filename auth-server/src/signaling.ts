import { WebSocketServer, WebSocket } from "ws";
import type { Server } from "http";
import { pool } from "./auth.js";

interface PeerConnection {
  userId: string;
  sessionId: string;
  ws: WebSocket;
}

interface SignalingMessage {
  type: "join" | "offer" | "answer" | "ice-candidate" | "leave" | "error" | "peer-joined" | "peer-left";
  sessionId?: string;
  userId?: string;
  payload?: any;
}

// Track active connections by session
const sessions = new Map<string, Map<string, PeerConnection>>();

export function setupSignaling(server: Server) {
  const wss = new WebSocketServer({ server, path: "/ws/signaling" });

  wss.on("connection", (ws) => {
    let currentUserId: string | null = null;
    let currentSessionId: string | null = null;

    ws.on("message", async (data) => {
      try {
        const message: SignalingMessage = JSON.parse(data.toString());

        switch (message.type) {
          case "join":
            await handleJoin(ws, message, (userId, sessionId) => {
              currentUserId = userId;
              currentSessionId = sessionId;
            });
            break;

          case "offer":
          case "answer":
          case "ice-candidate":
            handleSignal(ws, message, currentSessionId, currentUserId);
            break;

          case "leave":
            handleLeave(currentSessionId, currentUserId);
            break;

          default:
            sendError(ws, "Unknown message type");
        }
      } catch (err) {
        console.error("Signaling error:", err);
        sendError(ws, "Invalid message format");
      }
    });

    ws.on("close", () => {
      if (currentSessionId && currentUserId) {
        handleLeave(currentSessionId, currentUserId);
      }
    });

    ws.on("error", (err) => {
      console.error("WebSocket error:", err);
    });
  });

  console.log("WebRTC signaling server ready on /ws/signaling");
}

async function handleJoin(
  ws: WebSocket,
  message: SignalingMessage,
  setContext: (userId: string, sessionId: string) => void
) {
  const { sessionId, userId } = message;

  if (!sessionId || !userId) {
    sendError(ws, "Missing sessionId or userId");
    return;
  }

  // Verify the session exists and user is part of it
  const result = await pool.query(
    `SELECT ls.*, c.user_a, c.user_b
     FROM live_sessions ls
     JOIN connections c ON ls.connection_id = c.id
     WHERE ls.id = $1 AND ls.active = true
       AND (c.user_a = $2 OR c.user_b = $2)`,
    [sessionId, userId]
  );

  if (result.rows.length === 0) {
    sendError(ws, "Invalid session or unauthorized");
    return;
  }

  // Get or create session room
  if (!sessions.has(sessionId)) {
    sessions.set(sessionId, new Map());
  }

  const room = sessions.get(sessionId)!;

  // Check if already connected
  if (room.has(userId)) {
    // Close old connection
    const oldConn = room.get(userId);
    oldConn?.ws.close();
  }

  // Add to room
  const connection: PeerConnection = { userId, sessionId, ws };
  room.set(userId, connection);
  setContext(userId, sessionId);

  // Notify other peers
  room.forEach((peer, peerId) => {
    if (peerId !== userId && peer.ws.readyState === WebSocket.OPEN) {
      peer.ws.send(JSON.stringify({
        type: "peer-joined",
        userId,
      }));
    }
  });

  // Send list of existing peers to new joiner
  const peers = Array.from(room.keys()).filter((id) => id !== userId);
  ws.send(JSON.stringify({
    type: "join",
    sessionId,
    peers,
  }));

  console.log(`User ${userId} joined session ${sessionId}. Peers: ${room.size}`);
}

function handleSignal(
  ws: WebSocket,
  message: SignalingMessage,
  sessionId: string | null,
  fromUserId: string | null
) {
  if (!sessionId || !fromUserId) {
    sendError(ws, "Not in a session");
    return;
  }

  const room = sessions.get(sessionId);
  if (!room) {
    sendError(ws, "Session not found");
    return;
  }

  const targetUserId = message.userId;
  if (!targetUserId) {
    sendError(ws, "Target user not specified");
    return;
  }

  const targetPeer = room.get(targetUserId);
  if (!targetPeer || targetPeer.ws.readyState !== WebSocket.OPEN) {
    sendError(ws, "Target peer not connected");
    return;
  }

  // Forward the signal to the target peer
  targetPeer.ws.send(JSON.stringify({
    type: message.type,
    userId: fromUserId,
    payload: message.payload,
  }));
}

function handleLeave(sessionId: string | null, userId: string | null) {
  if (!sessionId || !userId) return;

  const room = sessions.get(sessionId);
  if (!room) return;

  room.delete(userId);

  // Notify other peers
  room.forEach((peer) => {
    if (peer.ws.readyState === WebSocket.OPEN) {
      peer.ws.send(JSON.stringify({
        type: "peer-left",
        userId,
      }));
    }
  });

  // Clean up empty rooms
  if (room.size === 0) {
    sessions.delete(sessionId);
  }

  console.log(`User ${userId} left session ${sessionId}`);
}

function sendError(ws: WebSocket, error: string) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "error", payload: { error } }));
  }
}
