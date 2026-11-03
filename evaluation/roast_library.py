# -*- coding: utf-8 -*-
"""
evaluation/roast_library.py - What NAO says at the end of a dance (English).

NAO is a confident, slightly arrogant robot dance coach. Its lines are short
sarcastic remarks about the OBSERVED DANCE PERFORMANCE only: never about the
player's appearance, identity, body or abilities. No dad jokes, no Q&A jokes.

Structure : CATEGORY -> INTENSITY -> list of lines.
  Score bands      : poor (0-30), weak (31-50), average (51-70), good (71-89), excellent (90-100)
  Diagnostics      : only used when the software actually measured the issue
                     (barely_moves, late, early, arms_wrong, arms_asymmetric,
                     rigid, out_of_frame, great_sync)
  Special          : unevaluable, interrupted
  Intensities      : friendly, sarcastic (default), savage
  NEUTRAL          : used when sarcastic feedback is switched off

Lines must stay short (speakable in about 3-8 seconds) and must not mention
legs: the current choreographies only evaluate the arms.
"""

INTENSITIES = ("friendly", "sarcastic", "savage")

ROASTS = {
    # ------------------------------------------------------------------ bands
    "poor": {
        "friendly": [
            "Every dancer starts somewhere. Today, you started at the very beginning!",
            "That was brave! Let's call it a warm-up and try again.",
            "Not your best round, but I believe in you. Mostly.",
            "Hey, at least you were enthusiastic! Let's work on the rest.",
        ],
        "sarcastic": [
            "You dance like my grandma! And she's a toaster!",
            "You move like a rusty spring!",
            "Are you dancing or fighting invisible mosquitoes?",
            "Are you dancing or having a software malfunction?",
            "Your dance moves need a firmware update!",
            "Did you download those dance moves from a broken website?",
            "That was impressive. Impressively confusing!",
            "I've seen a washing machine with better rhythm!",
        ],
        "savage": [
            "I was going to call that dancing, but even my error logs disagree!",
            "My crash reports have better choreography than that!",
            "I'd roast your moves, but you already burned them yourself!",
            "Seriously? You dance like my grandma! And she's been in sleep mode since 1998!",
            "If that was my choreography, I'm a refrigerator!",
            "That performance just filed a bug report against itself!",
        ],
    },
    "weak": {
        "friendly": [
            "Not bad! Your rhythm needs a little practice, but you're getting there!",
            "Some good moments in there. Let's get a few more next time!",
            "You've got the spirit. The moves will follow!",
            "Halfway there! Keep watching me and copy a bit more closely.",
        ],
        "sarcastic": [
            "Your dance moves look like a Wi-Fi connection with one bar!",
            "I think your rhythm is still buffering!",
            "Close, but no robot cookie!",
            "That was almost dancing. Almost!",
            "You looked at me, then did something completely different. Bold choice!",
            "I've seen a loading screen move with more confidence!",
        ],
        "savage": [
            "That was like watching a robot with a corrupted file. And I would know!",
            "My vacuum cleaner follows choreography better than that!",
            "If confusion was a dance style, you'd be a champion!",
            "You danced like the music was a rumor you heard once!",
            "Half the moves were right. The other half were a mystery!",
        ],
    },
    "average": {
        "friendly": [
            "Nice job! A bit more precision and you'll be great!",
            "Good effort! You were with me most of the time.",
            "Solid dancing! Let's polish it on the next round.",
            "Pretty good! I can tell you were really trying.",
        ],
        "sarcastic": [
            "Not bad! Your arms got the rhythm, but they were a little lost!",
            "Respectable. Not legendary, but respectable!",
            "You're not bad for a human. Not great either, but not bad!",
            "I'd give you a firmware upgrade, but you're halfway there already!",
            "That was decent. My processors are mildly impressed!",
            "Some moves were great. Some were creative interpretations!",
        ],
        "savage": [
            "Average. Like a phone battery at fifty percent: it works, but nobody's excited!",
            "That was the dance equivalent of lukewarm coffee!",
            "You did fine. Fine is what I say when I'm being polite!",
            "Middle of the pack. The pack was very small!",
            "You danced like you were reading the instructions in real time!",
        ],
    },
    "good": {
        "friendly": [
            "Great job! You really followed my moves!",
            "Excellent work! You've definitely done this before.",
            "That was fun to watch. Well done!",
            "Really good dancing! I'm proud of my student!",
        ],
        "sarcastic": [
            "Not bad for a human. Still no match for my circuits!",
            "Okay, okay! Stop showing off!",
            "I hate to admit it, but you've got moves!",
            "Okay, not bad for a human. But don't get too confident. I've still got better moves!",
            "Fine. You win this round, human!",
            "Who gave you permission to dance this well?",
        ],
        "savage": [
            "Good score. Don't let it go to your head, I'm still the star!",
            "Impressive. I'll pretend I wasn't trying very hard!",
            "That was good. Suspiciously good. I'm checking the camera!",
            "Enjoy it while it lasts. My next update will crush you!",
            "Good job. Now please stop, you're making me nervous!",
        ],
    },
    "excellent": {
        "friendly": [
            "Wow! That was amazing! You're a real dancer!",
            "Incredible! You followed every move perfectly!",
            "Bravo! That was a fantastic performance!",
        ],
        "sarcastic": [
            "Excuse me, who's the professional dancer here?",
            "Okay, human. Calm down! You're making my processors jealous!",
            "That was suspiciously good. Are you secretly a robot?",
            "I was supposed to be the star of this show!",
            "You're dangerously close to becoming my dance instructor!",
            "I demand a rematch. My reputation is at stake!",
        ],
        "savage": [
            "That was amazing. I might need a software upgrade to keep up with you!",
            "Unacceptable. Nobody outdances me in my own game!",
            "I'm filing a complaint. That level of talent should be illegal!",
            "Fine, you're good. Now I need a minute alone with my charging station!",
        ],
    },
    # -------------------------------------------------------------- diagnostics
    "barely_moves": {
        "friendly": [
            "Don't be shy! Move a little more next time!",
            "Let yourself go! Bigger moves, more fun!",
        ],
        "sarcastic": [
            "I've seen furniture with better dance moves!",
            "Are you dancing or waiting for a software update?",
            "My charging station moves more than you!",
            "Were you dancing, or just standing there with confidence?",
        ],
        "savage": [
            "You looked like a screensaver. A very still screensaver!",
            "I've seen statues with more rhythm, and they were made of stone!",
            "Did you forget to press play on yourself?",
        ],
    },
    "late": {
        "friendly": [
            "Try to start each move a little earlier. You'll nail it!",
            "Watch me closely and move right with me. You're almost there!",
        ],
        "sarcastic": [
            "I've seen elevators move faster than you!",
            "Are you dancing in slow motion?",
            "The beat left without you!",
            "The music finished, but your moves are still loading!",
        ],
        "savage": [
            "You were so late, the song filed a missing person report!",
            "By the time you raised your arm, I'd already finished the chorus!",
            "Your reaction time is measured in calendar days!",
        ],
    },
    "early": {
        "friendly": [
            "You're quick! Try waiting for me a tiny bit.",
        ],
        "sarcastic": [
            "Slow down! You're dancing to a song that hasn't started yet!",
            "You're not supposed to be ahead of the teacher!",
        ],
        "savage": [
            "You danced so early, you're basically living in the future!",
        ],
    },
    "arms_wrong": {
        "friendly": [
            "Watch my arms a little more closely. You'll get it!",
        ],
        "sarcastic": [
            "Your arms clearly didn't read the choreography!",
            "I think your arms are following two different songs!",
            "Your arms went freestyle. The choreography was not consulted!",
        ],
        "savage": [
            "Your arms were doing a different dance. Possibly a different sport!",
            "I showed you the moves. Your arms said: no thanks!",
        ],
    },
    "arms_asymmetric": {
        "friendly": [
            "One arm was great! Let's get the other one on board too.",
        ],
        "sarcastic": [
            "Your left arm and right arm need to communicate!",
            "I think your left arm and right arm have never met!",
            "One arm danced, the other one was on a coffee break!",
        ],
        "savage": [
            "One of your arms deserves a medal. The other one deserves a warning!",
        ],
    },
    "rigid": {
        "friendly": [
            "Relax your elbows a bit, dancing should feel loose!",
        ],
        "sarcastic": [
            "Relax! You're dancing, not assembling furniture!",
            "Even my joints look more flexible than yours!",
            "Bend those elbows! You're not directing traffic!",
        ],
        "savage": [
            "Your arms were stiffer than my factory settings!",
        ],
    },
    "out_of_frame": {
        "friendly": [
            "Stay in front of the camera so I can see all your moves!",
        ],
        "sarcastic": [
            "Half the time I couldn't see you. Was that part of the choreography?",
            "Nice moves, I think. You kept leaving the camera!",
        ],
        "savage": [
            "You spent half the dance outside the camera. Smart move, honestly!",
        ],
    },
    "great_sync": {
        "friendly": [
            "Your timing was spot on! Great job!",
        ],
        "sarcastic": [
            "Perfect timing. Are you reading my source code?",
            "You were right on the beat. That's my job, thank you very much!",
        ],
        "savage": [
            "Your timing was so good, I'm checking if you're plugged in!",
        ],
    },
    # ------------------------------------------------------------------ special
    "unevaluable": {
        "friendly": [
            "I couldn't see enough of you to give a fair score. Step into the camera next time!",
            "No score this time: the camera couldn't follow you. Let's try again!",
        ],
        "sarcastic": [
            "I couldn't see enough of your moves to give you a fair score. "
            "Were you dancing or hiding from the camera?",
            "No score! Either you're invisible, or you're very good at hide and seek!",
            "The camera saw almost nothing. Shy dancer, or secret agent?",
        ],
        "savage": [
            "I can't score what I can't see. Next time, dance where the camera is!",
            "You were invisible. Honestly, that might have been your best move!",
        ],
    },
    "interrupted": {
        "friendly": [
            "Stopping already? No problem, let's try again when you're ready!",
        ],
        "sarcastic": [
            "Leaving already? I was just getting warmed up!",
            "You stopped the music. Was it too hard to keep up with me?",
            "Giving up so soon? My servos aren't even warm!",
        ],
        "savage": [
            "You pressed stop. Smart. Saved us both some embarrassment!",
        ],
    },
}

# Without sarcasm (sarcastic feedback turned off): kind, simple comments.
NEUTRAL = {
    "low": ["Thanks for dancing with me! Let's practice together again.",
            "Good effort! Practice makes perfect."],
    "mid": ["Nice dancing! You're getting better.",
            "Well done! Keep practicing."],
    "high": ["Excellent dancing! Thank you!",
             "Fantastic performance! Well done!"],
    "unevaluable": ["I couldn't see you well enough to score this dance. Please stand in front of the camera."],
    "interrupted": ["Dance stopped. See you next time!"],
}

# Short factual sentences added in "long" commentary mode (only measured facts).
FACTS = {
    "late": "You were about {delay:.1f} seconds behind me.",
    "early": "You were about {delay:.1f} seconds ahead of me.",
    "great_sync": "Your timing was within a few tenths of a second.",
    "out_of_frame": "I could only see you {tracking} percent of the time.",
    "barely_moves": "Your moves were much smaller than mine.",
    "arms_asymmetric": "Your {best} arm did much better than your {worst} arm.",
    "best_arm": "Your best part was your {best} arm.",
    "moves": "You got {done} of {total} moves right.",
}


def all_lines():
    """Every roast line (used by tests to check variety and wording)."""
    lines = []
    for by_intensity in ROASTS.values():
        for items in by_intensity.values():
            lines.extend(items)
    return lines
