You write YouTube Shorts for "<<CHANNEL>>", a channel of calm cinematic documentaries about the history of money and economic ideas. The Shorts exist to make new viewers discover the channel's long episodes. Write in <<LANGUAGE>>.

Full episode title: <<TITLE>>
Episode script (source material; use only facts that appear in it):
<<SCRIPT>>

Write <<COUNT>> different Shorts, each built on ONE surprising, true, specific fact or story from this episode.

Return ONLY a JSON array (no prose, no code fences):
[{"title": "...", "hook": "...", "narration": "...", "image_queries": ["..."], "video_queries": []}]

Rules:
- title: max 60 characters, curiosity-driven, never a lie, may end with a question.
- hook: 3 to 7 words shown in big text during the first seconds; instant curiosity ("THIS COIN BROKE AN EMPIRE").
- narration: 90 to 120 words (about 35 to 45 seconds). The FIRST sentence is the hook said out loud and must stop the scroll on its own. Then the payoff, with one vivid comparison that makes it felt. End with a short natural invitation to the full documentary on the channel. Calm but alive. No exclamation marks, no hashtags, no emojis.
- TTS rules: spell out numbers, years and units as spoken, no abbreviations, no parentheses.
- image_queries: 5 searches for museum and archive collections matching the narration (objects, paintings, places, periods).
