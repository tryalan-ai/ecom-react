import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';

/**
 * Format elapsed milliseconds Claude Code-style:
 * - under 60s: "3.2s"
 * - 60s+: "1m 3s"
 */
export const formatElapsed = (elapsedMs) => {
  const totalSeconds = Math.max(0, elapsedMs / 1000);
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(1)}s`;
  }
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}m ${seconds}s`;
};

/**
 * InlineLoader — Claude Code / Codex CLI / T3 Chat-style inline streaming indicator.
 *
 * Pattern (researched):
 * - Claude Code: `✻ Crunching… (32s · ↓ 3,678 tokens)` — spinner verb + elapsed
 *   recomputed from wall clock every render, plus live token count and current
 *   tool/step. Completion flips to past tense ("Brewed for Ns").
 * - Codex CLI TUI: `• Working (10s • esc to interrupt)` /
 *   `✽ Jitterbugging… (4m 26s · ↓ 7.1k tokens)` — spinner + elapsed + tokens.
 * - T3 Chat / web chat: animated dots inside the assistant bubble while waiting,
 *   then below streamed content while streaming; reasoning stays open as a
 *   collapsible "Thinking…" disclosure until done.
 *
 * This component is complementary to page-level collapse/skeleton states —
 * render it inline in the content area while streaming/loading, and keep the
 * existing skeleton or collapsible sections intact underneath.
 */
const InlineLoader = ({
  status = 'Working',
  detail = null,
  count = null,
  countLabel = 'items',
  startedAt = null,
  showElapsed = true,
  showSpinner = true,
  variant = 'inline',
  className = '',
}) => {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!showElapsed) return undefined;
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, [showElapsed]);

  const elapsedMs = startedAt != null ? Math.max(0, now - startedAt) : null;

  const metadataParts = [];
  if (showElapsed && elapsedMs != null) {
    metadataParts.push(formatElapsed(elapsedMs));
  }
  if (detail) {
    metadataParts.push(detail);
  }
  if (count != null) {
    metadataParts.push(`↓ ${count} ${countLabel}`);
  }
  const metadata = metadataParts.join(' · ');

  if (variant === 'centered') {
    return (
      <div
        role="status"
        aria-live="polite"
        className={`flex flex-col items-center justify-center gap-2 py-8 text-center ${className}`}
      >
        {showSpinner && (
          <Loader2 className="w-8 h-8 text-primary-600 animate-spin" aria-hidden="true" />
        )}
        <p className="text-sm font-medium text-gray-900">
          {status}
          <span className="animate-pulse">…</span>
        </p>
        {metadata && <p className="text-xs text-gray-500">({metadata})</p>}
      </div>
    );
  }

  if (variant === 'compact') {
    return (
      <div
        role="status"
        aria-live="polite"
        className={`flex items-center gap-2 text-sm text-gray-600 ${className}`}
      >
        {showSpinner && (
          <Loader2 className="w-4 h-4 text-primary-600 animate-spin shrink-0" aria-hidden="true" />
        )}
        <span className="font-medium text-gray-700">
          {status}
          <span className="animate-pulse">…</span>
        </span>
        {metadata && <span className="text-xs text-gray-500">({metadata})</span>}
      </div>
    );
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center gap-2.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-600 shadow-sm ${className}`}
    >
      {showSpinner && (
        <Loader2 className="w-4 h-4 text-primary-600 animate-spin shrink-0" aria-hidden="true" />
      )}
      <span className="font-medium text-gray-900">
        {status}
        <span className="animate-pulse">…</span>
      </span>
      {metadata && <span className="text-xs text-gray-500">({metadata})</span>}
    </div>
  );
};

export default InlineLoader;
