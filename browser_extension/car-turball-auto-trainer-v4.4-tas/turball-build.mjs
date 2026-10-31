// Public asset identification only. Never inspect HAR headers, accounts or tokens.
export function assetPath(url) {
  const parsed = new URL(url);
  if (parsed.origin !== 'https://turball.io' || !/^\/assets\/app\/chunk-[\w-]+\.js$/.test(parsed.pathname))
    throw new Error('Not a Turball gameplay asset');
  return parsed.pathname;
}

export function exportsStartGame(source) {
  return /\bexport\s*\{[^}]{0,1024}\b(?:as\s+)?startGame\b[^}]*\}/.test(source)
    || /\bexport\s+(?:async\s+)?function\s+startGame\s*\(/.test(source);
}

export function gameplayDependency(source, url) {
  // The lobby destructures startGame from its lazy import. Bound the search so
  // an unrelated import elsewhere in a shared chunk cannot become the target.
  const match = /\{\s*startGame(?:\s*:\s*[$\w]+)?\s*\}\s*=\s*await[^;]{0,300}?\bimport\(["'](\.\/chunk-[\w-]+\.js)["']\)/.exec(source);
  return match ? assetPath(new URL(match[1], url).href) : null;
}
