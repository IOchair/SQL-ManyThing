# Dashboard TUI — Full Abstraction Frame Trace

Actual execution trace using `block_content_full` (post-scope_end_offset fix, 2026-06-02):

```
═══ A* BUDGET FRAME  #1 ═══
QUERY: Dashboard TUI — how does the browser connect to the agent?
LAYERS:
  1. frontend_component: xterm.js terminal UI (ChatPage.tsx)
  2. api_layer: /api/pty WebSocket endpoint (web_server.py)
  3. backend_domain: PtyBridge.spawn (pty_bridge.py)
  4. sidecar_transport: tui_gateway WSTransport (ws.py)
```

## Execution (post-fix: block_content_full, 4 queries)

→ `[budget] L1-P: g=1` — FTS5 MATCH `xterm Terminal ChatPage` → ChatPage.tsx (rank -5.2)
→ `[budget] L1-E: g=2` — block_content_full depth=0 → 29441 bytes (full component: xterm.js + WebSocket + resize + clipboard)
→ `[budget] L2-P: g=3` — block_content LIKE `%async def pty_ws%` → web_server.py depth=0
→ `[budget] L2-E: g=4` — block_content_full depth=0 → 4303 bytes (auth→accept→spawn→pump_pty→write→resize→cleanup)
→ `[budget] L3-P: g=5` — block_content LIKE `%def spawn%` → pty_bridge.py depth=1
→ `[budget] L3-E: g=6` — block_content_full depth=1 → 1850 bytes (full method: TERM backfill→PtyProcess.spawn→return PtyBridge)
→ `[budget] L4-P: g=7` — FTS5 MATCH `handle_ws tui_gateway` → tui_gateway/ws.py
→ `[budget] L4-E: g=8` — block_content_full depth=1 → WSTransport dispatch → AIAgent
✓ goal: block_content_full returns complete body for all 4 layers (8 queries total)

## Pre-fix comparison (block_content only, 10+ queries)

Before `scope_end_offset`/`block_content_full`, the same 4 layers required redundant substr stitching:
- L1-E: depth=1 `block_content` was only the immediate segment header → needed code_search fallback (~29576 bytes of raw JSX)
- L2-E: depth=0 `block_content` truncated at 512 bytes → 2 extra substr queries
- L3-E: depth=1 `block_content` was only signature+docstring (512 bytes) → 3 extra substr queries to stitch depth=2/3/4 segments
- L4-E: depth=1 `block_content` → acceptable for this specific file but fragile

Multi-step substr stitching anti-pattern eliminated: `substr(f.content, ve.start_offset, ve.end_offset - ve.start_offset)` chaining.

## Architecture

Browser (xterm.js) → WebSocket /api/pty → FastAPI pty_ws() → POSIX PTY → node entry.js → Ink React TUI + Python tui_gateway → AIAgent

Sidecar: /api/ws → WSTransport → tui_gateway.server.dispatch (same handler as Ink stdio)
Pub-sub: tui_gateway.entry → /api/pub → fan-out → /api/events → ChatSidebar (tool-call feed)
