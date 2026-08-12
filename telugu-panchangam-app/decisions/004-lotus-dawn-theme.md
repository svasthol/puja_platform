# ADR 004 — Lotus Dawn as the Application Theme

**Date:** March 2026
**Status:** Accepted

## Context

Six distinct themes were prototyped and compared:
1. Night Sky (dark indigo + saffron)
2. Palm Leaf Manuscript (gold-brown, scholarly)
3. Temple Stone (warm terracotta, light)
4. Lotus Dawn (sunrise orange-pink, light)
5. Ink & Paper (editorial, cream + black)
6. Royal Maroon (dark maroon + gold)

## Decision

**Lotus Dawn** — warm sunrise gradient header (saffron → orange → gold), cream background, Lora body font, Playfair Display italic for Sanskrit/Telugu terms.

## Reasons

- Matches the emotional register of opening a Panchangam — the day begins at sunrise
- Warm saffron-orange evokes kumkum, marigold, lamp flame — central to Telugu devotional culture
- Broadest cross-generational appeal — works for grandmothers and grandchildren alike
- Light mode is preferred by older users and temple settings
- Card-based Panchanga layout with rounded corners is excellent for mobile
- Fonts are distinctive and refined: Noto Sans Telugu (authentic), Playfair Display (elegant italic for Sanskrit terms), Lora (warm body text)
- Most other Telugu Panchangam apps are either plain white or dark blue — Lotus Dawn is immediately recognisable

## Design Tokens

```
bg:        #FFF6EE  warm cream
header:    #D4603A → #E8875A → #D4A547  sunrise gradient
text:      #1A0800  near-black warm
textSoft:  #6B3010  deep warm brown
accent:    #C04020  burnt orange
label:     #8B4020  terracotta
gold:      #A07000  rich gold (Purnima, festivals)
danger:    #8B0000  deep red (Rahukalam)
auspicious:#167040  deep green (Tarabalam)
```
