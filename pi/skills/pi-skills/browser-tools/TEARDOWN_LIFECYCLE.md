# Browser Teardown Lifecycle

Closing a headful browser running inside a virtual framebuffer (Xvfb) with active session profiles requires a highly coordinated, multi-layered teardown. If you just yank the plug with a crude `kill -9`, two bad things happen: **Chromium corrupts the profile cache** (meaning your hard-won 2FA session state doesn't save correctly), and **Xvfb leaks virtual display sockets** in `/tmp/.X11-unix/`, eventually exhausting system resources.

To prevent this, the pi browser-tools and eigent substrate uses a deterministic **4-Step Teardown Chain** wrapped in defensive Node.js lifecycle hooks.

## The Clean Closing Lifecycle

### 1. The CDP Handshake (`Browser.close`)

Before touching the operating system's process tree, the agent issues a graceful shutdown command directly through the Chrome DevTools Protocol (CDP) connection.

```javascript
// Graceful protocol-level teardown
await client.send('Browser.close');
```

**Why it matters:** This tells Chromium to begin an orderly exit. It flushes the memory cache, writes active session cookies, updates local storage, and finalizes IndexedDB states to the disk directory. Without this step, your `fs.cpSync()` routine in the pi layer would copy an incomplete, corrupted profile back to storage.

### 2. PID Tree Termination

Chromium uses a multi-process architecture (a browser process, a GPU process, network utilities, and individual renderers for every tab). If the CDP connection is lost or times out during shutdown, the agent falls back to killing the process group.

- **The Mechanism:** The agent tracks the root `child_process.spawn()` PID. Instead of killing *just* that ID, it traverses the OS process tree to find all child processes belonging to that group.
- **The Signal:** It sends a `SIGTERM` (Signal 15) to allow graceful handling, waiting for a short grace period before escalating to `SIGKILL` (Signal 9) only as an absolute last resort.

### 3. Xvfb Virtual Display Teardown

Because the browser is running headful via an X11 server illusion, the virtual display process (Xvfb) must be cleaned up in tandem with Chromium.

- **Lockfile Erasure:** When Xvfb spins up on a specific display port (e.g., `:99`), it creates a unix socket lockfile at `/tmp/.X10-lock`.
- **The Agent's Job:** The cleanup routine ensures the Xvfb process is killed, and explicitly verifies that its respective socket files in `/tmp` are wiped clean so the display number can be instantly reused by the next worker event in your NATS queue.

### 4. The `try/finally` & Process Signal Guardrails

The most critical part of the cleanup isn't *how* it kills the processes, but *where* that code lives. The architecture ensures that no matter how catastrophic a script failure is, the cleanup path is unavoidable.

#### Codebase Execution Pattern

The stack structures its operations using strict block isolation and global process listeners:

```javascript
async function executeBrowserTask() {
  let browserProcess = null;
  let xvfbProcess = null;

  try {
    // 1. Spin up Xvfb & Launch Chromium
    browserProcess = await launchChromium();
    
    // 2. Perform elite automation (OAuth, Scrapes, etc.)
    await navigateAndInteract();
    
  } finally {
    // GUARANTEED EXECUTION: Runs even if timeouts or unhandled exceptions occur above
    console.log("Initiating clean substrate teardown...");
    
    if (browserProcess) {
      try { await gracefullyCloseCDP(); } catch (e) { /* ignore fallback */ }
      browserProcess.kill('SIGTERM');
    }
    
    if (xvfbProcess) {
      xvfbProcess.kill('SIGTERM');
      await cleanDisplaySockets();
    }
  }
}

// Global Emergency Overrides
process.on('SIGINT',  () => { emergencyCleanup(); process.exit(1); });
process.on('SIGTERM', () => { emergencyCleanup(); process.exit(1); });
process.on('exit',    () => { emergencyCleanup(); });
```

## Architectural Comparison: Clean vs. Dirty Closure

| Metric | Clean Shutdown (`Browser.close` + Teardown) | Dirty Shutdown (`kill -9` / Raw Crash) |
|--------|---------------------------------------------|----------------------------------------|
| **Session State / Cookies** | Fully serialized and flushed to disk. Persistent. | Lost, incomplete, or marked as corrupted by Chrome. |
| **Profile Integrity** | Safe for subsequent `fs.cpSync` operations. | Preferences file locks stay active; causes "Chrome did not shut down correctly" warnings next launch. |
| **System Resources** | Process table completely cleared; `/tmp` sockets released. | Orphaned zombie processes; `/tmp/.X11-unix` leaks slowly starve the OS. |
| **Reusability** | Next worker can immediately lease the display/profile. | Next worker blocks on file locks or display-in-use errors. |

By keeping the execution logic anchored in a strict `finally` block and catching OS-level termination signals, the system guarantees that your host machine maintains a pristine slate—allowing your worker pools to run thousands of sequential automation cycles without degrading performance.
