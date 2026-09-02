/** Build a terminal stream error while preserving provider-supplied text. */
export function createTerminalStreamError(payload = {}) {
  const rawError = payload.error;
  // Prefer the most descriptive source: provider text, provider error, then the
  // server-supplied message, and only fall back to a bare "Error <status>" when
  // nothing else is available.
  const rawMessage = (
    payload.text
    || (typeof rawError === 'string' ? rawError : rawError?.message)
    || payload.message
  );
  const message = decorateStreamError(rawMessage, payload.status);
  const error = new Error(message);
  error.name = 'TerminalStreamError';
  error.terminalStreamError = true;
  error.status = payload.status;
  return error;
}

/**
 * Turn a raw provider/server error into something a normal user can act on.
 * Never returns just "Error 502" — it always explains what the code actually
 * means and what to do next.
 */
export function decorateStreamError(rawMessage, status) {
  const raw = (rawMessage || '').trim();
  if (raw && !/^error\s*\d{3}$/i.test(raw)) return raw;

  const statusLabels = {
    400: 'Bad Request — the model refused the request (often a malformed prompt or tool call). Try rewording and send again.',
    401: 'Unauthorized — the API key is missing or wrong. Check the model/endpoint credentials in Settings.',
    402: 'Payment Required — the API account is out of credits or billing is paused. Top up the account to continue.',
    403: 'Forbidden — the API key lacks permission for this model. Check endpoint access.',
    404: 'Not Found — the model or endpoint does not exist. Verify the model name/URL in Settings.',
    408: 'Request Timeout — the model took too long to respond. Retry.',
    429: 'Rate Limited — too many requests too quickly. Wait a few seconds and try again.',
    500: 'Server Error — the model provider had an internal failure. Retry shortly.',
    502: 'Bad Gateway — the model/endpoint host failed to relay the request (commonly an upstream outage or a proxy issue at the provider). Retry later or try another model.',
    503: 'Service Unavailable — the model host is down or starting up. Wait and retry.',
    504: 'Gateway Timeout — the model host took too long and the gateway gave up. Retry or try another model.',
  };

  if (status && statusLabels[status]) {
    return `Error ${status}: ${statusLabels[status]}`;
  }
  if (status) {
    return `Error ${status} — the model/endpoint request failed. Check the endpoint in Settings and retry.`;
  }
  return raw || 'The stream failed without a provided reason. Retry or try another model.';
}

/** Only connection-class stream failures are safe to resubmit automatically. */
export function isRecoverableStreamError(error) {
  if (!error || error.terminalStreamError || error.name === 'TerminalStreamError') return false;
  if (error.name === 'TypeError') return true;
  const message = (error.message || '').toLowerCase();
  if (/\btool\b|unsupported|json|parse|\b4\d\d\b|\b5\d\d\b/.test(message)) return false;
  return /network|fetch|connection|reset|closed|aborted|stream|tim(?:e|ed)\s?out|econn|eof/.test(message);
}
