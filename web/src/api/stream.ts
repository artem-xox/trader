/** Read a Server-Sent Events response as an async iterable of parsed frames.
 *
 * `EventSource` is not usable here: it only issues GET requests, and every
 * streaming endpoint in this app is a POST. So the stream is read by hand off
 * `fetch`'s ReadableStream.
 *
 * The wire format is the subset FastAPI emits (`app/streaming.py`): frames are
 * separated by a blank line, payload lines start with `data:`, and lines
 * starting with `:` are keepalive comments — ignored here, but they are the
 * reason a long quiet run does not look like a dead connection.
 */
export async function* streamSse<T>(
  url: string,
  body: unknown,
  options: { headers?: Record<string, string>; signal?: AbortSignal } = {},
): AsyncGenerator<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`${url} responded ${response.status}`);
  }
  if (response.body === null) {
    throw new Error(`${url} responded without a body`);
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += value;

    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of frame.split('\n')) {
        if (line.startsWith('data:')) {
          yield JSON.parse(line.slice(5).trim()) as T;
        }
      }
      boundary = buffer.indexOf('\n\n');
    }
  }
}
