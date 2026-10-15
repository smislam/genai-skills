'use strict';
// Minimal glob matching for repo-relative paths with forward slashes (Node 18 has no built-in).
// Supports **, *, ?, {a,b}, and character classes [...]. A glob without "/" matches the base name.

const cache = new Map();

function globToRegExp(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*') {
      if (glob[i + 1] === '*') {
        // "**/" matches zero or more directories; a trailing "**" matches everything below.
        if (glob[i + 2] === '/') { re += '(?:.*/)?'; i += 2; } else { re += '.*'; i += 1; }
      } else {
        re += '[^/]*';
      }
    } else if (c === '?') {
      re += '[^/]';
    } else if (c === '{') {
      const end = glob.indexOf('}', i);
      if (end < 0) { re += '\\{'; continue; }
      re += '(?:' + glob.slice(i + 1, end).split(',').map((alt) => globToRegExp(alt).source.slice(1, -1)).join('|') + ')';
      i = end;
    } else if (c === '[') {
      const end = glob.indexOf(']', i);
      if (end < 0) { re += '\\['; continue; }
      re += '[' + glob.slice(i + 1, end).replace(/\\/g, '\\\\') + ']';
      i = end;
    } else {
      re += c.replace(/[.+^$()|\\]/g, '\\$&');
    }
  }
  return new RegExp('^' + re + '$');
}

function compile(glob) {
  if (!cache.has(glob)) cache.set(glob, globToRegExp(glob));
  return cache.get(glob);
}

function matches(relPath, glob) {
  const target = glob.includes('/') ? relPath : relPath.slice(relPath.lastIndexOf('/') + 1);
  return compile(glob).test(target);
}

function matchesAny(relPath, globs) {
  return (globs || []).some((g) => matches(relPath, g));
}

module.exports = { globToRegExp, matches, matchesAny };
