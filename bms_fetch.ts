// Standard Bun HTTP client, matching the successful Railway access probe.
// No browser impersonation, cookies, proxies, or challenge solving.
const input = JSON.parse(await Bun.stdin.text());
try {
  const url = new URL(input.url);
  url.search = new URLSearchParams(input.params).toString();
  const response = await fetch(url, {headers: input.headers, signal: AbortSignal.timeout(20000)});
  const text = await response.text();
  console.log(JSON.stringify({
    status: response.status,
    challenge: response.headers.get('cf-mitigated') === 'challenge' || text.includes('cf-chl-'),
    denied: /access denied|you have been blocked/i.test(text),
    body: response.ok ? text : ''
  }));
} catch {
  process.exitCode = 1;
}
