// Shared profanity filter for lyrics display.
const _slurList = atob(
  "YmVhbmVyLGJlYW5lcnMsY2hpbmsyY2hpbmtzLGNoaW5reSxjb29uLGNvb25zLGNvb255LGNyYWNrZXIsY3JhY2tlcnMsY3VudCxjdW50cyxkYWdvLGRhZ29zLGR5a2UsZHlrZXMsZHlrZXksZXNraW1vLGZhZyxmYWdnb3QsZmFnZ290cyxmYWdzLGZhZ2csZmFnZ2V0LGZAZ2dvdCxmQGdnMHQsZ2lwc3ksZ29vayxneXBzeSxoYWpqaSxodW4samlnYWJvbyxqaWdnLGtpZ2Usa2lrZXMsa3JhdXQsY3l0ZSxuaWcsbmlnZyxuaWdnYSxuaWdnYXMsbmlnZ2F6LG5pZ2dlcixuaWdnZXJzLG5pYixtaWJiYSxuaWJidXMsbmlnZ3VoLG5pZ2dhaCxuaWdndWhzLG5pZ2dhaHMsbmlwLHBpa2V5LHBvcmNobW9ua2V5LHBvcmNoLW1vbmtleSxyYWdoZWFkLHJlZHNraW4scmV0YXJkLHJldGFyZGVkLHJldGFyZHMs c2FuZG5pZ2dlcixzYW5kLW5pZ2dlcixzaGVtYWxlLHNoZS1tYWxlLHNsYW50ZXllLHN sYW50LWV5ZSxzcGVhcmNodWNrZXIsc3BpYyxzcGljayxzcGljcyxzcGlrLHRvd2VsaGVh ZCx0cmFubmlzLHRyYW5ueSx0cmFubix0cjRubnksdHdhdCx3ZXRiYWNrLHdldGJhY2tz LHdvcCx3b3BzLHppcHBlcmhlYWQsanVuZ2xlYnVubnkseWFyZGFwZQ==".replace(
    /\s+/g,
    "",
  ),
).split(",");

// One alternation built at module load instead of one RegExp per entry per call.
// Longest-first so the longer variant of a prefix pair wins over the shorter one.
// Safe as a shared /g regex: String.replace resets lastIndex.
const _slurRegex = new RegExp(
  `\\b(?:${_slurList.filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .map((slur) => slur.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|")})\\b`,
  "gi",
);

function filterText(text) {
  if (!text) return text;
  return text.replace(_slurRegex, (match) => "*".repeat(match.length));
}
