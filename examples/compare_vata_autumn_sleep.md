# Plain RAG vs GraphRAG

**Question:** I'm Vata dominant, it's autumn, and I sleep badly. What should my evening look like?

```text

--- Plain RAG: retrieved passages ---
  [P1] 0.816  VBR Dinacharya — Personalised Daily Rhythm > Evening — Kapha Window (7:00–10:00 PM)   doshas=tridoshic
  [P2] 0.815  Varsha Ritu — Monsoon Seasonal Regimen > Nidra (Sleep) & Rest   doshas=vata
  [P3] 0.797  Sleep Protocols — Sleep Hygiene by Dosha and Season > Requirements   doshas=tridoshic
  [P4] 0.795  Ritucharya — Ayurvedic Seasonal Regimen (Comprehensive) > Vata Season (Late Fall / Early Winter — cold, dry,   doshas=tridoshic
  [P5] 0.790  Vasanta Ritu — Spring Seasonal Regimen > Sleep & Rest   doshas=kapha
  [P6] 0.786  VBR Dinacharya — Personalised Daily Rhythm > Early Morning — Vata Window (2:00–6:00 AM)   doshas=tridoshic

=== Plain RAG answer (gpt-6-luna) ===

For a Vata-dominant person in autumn, aim for a calm, warm, predictable evening. The seasonal guidance specifically describes **late fall/early winter** as Vata season; if that matches your autumn, emphasize warmth, grounding, and regularity. [P4]

**A simple evening routine**
- **Keep the timing steady.** Start winding down in time to be in bed around **9:30–10:00 PM**. Vata sleep guidance stresses consistency and suggests **8–9 hours** of sleep. [P3]
- **Choose grounding food and drink.** Favor warm, moist, nourishing foods; avoid cold, raw, or dry foods and iced drinks. [P4] A warm milk drink with Ashwagandha is suggested for Vata in the evening routine. [P1]
- **Slow down before bed.** Try gentle stretching or Restorative yoga, then light reading, journaling, or a quiet conversation. Dim the lights as bedtime approaches. [P1]
- **Add warmth and a soothing ritual.** Consider Abhyanga with warm sesame oil, followed by a warm bath and a gratitude practice. [P1, P4]
- **Keep your wake time consistent.** The Vata sleep guidance gives **5:30–6:00 AM** as a wake-time range. [P3]

**Note on sleep duration:** the sources differ: a monsoon-specific regimen says 7–8 hours, while the general Vata sleep protocol says 8–9 hours. For your Vata-focused autumn routine, the 8–9-hour guidance is the more directly relevant one; the 7–8-hour figure is given for monsoon. [P2, P3]

**Sources**
- sleep-protocols.md
- varsha.md

--- GraphRAG: retrieved passages ---
  [P1] 0.815 (graph score 0.875)  Varsha Ritu — Monsoon Seasonal Regimen > Nidra (Sleep) & Rest   doshas=vata
  [P2] 0.816 (graph score 0.836)  VBR Dinacharya — Personalised Daily Rhythm > Evening — Kapha Window (7:00–10:00 PM)   doshas=tridoshic
  [P3] 0.772 (graph score 0.832)  Varsha Ritu — Monsoon Seasonal Regimen > Vyayama (Exercise)   doshas=vata
  [P4] 0.778 (graph score 0.818)  Vata Dosha — The Principle of Movement > Balancing Approaches   doshas=vata
  [P5] 0.797 (graph score 0.817)  Sleep Protocols — Sleep Hygiene by Dosha and Season > Requirements   doshas=tridoshic
  [P6] 0.795 (graph score 0.815)  Ritucharya — Ayurvedic Seasonal Regimen (Comprehensive) > Vata Season (Late Fall / Early Winter — cold, dry,   doshas=tridoshic

=== GraphRAG answer (gpt-6-luna) ===

For an autumn Vata evening, aim for **warmth, calm, and a steady rhythm**:

- **7:00–8:30 PM:** Start winding down. Dim the lights; try gentle stretching or restorative yoga, then light reading, journaling, or a quiet conversation. [P2]
- **Before bed:** A warm bath and gentle Abhyanga with warm sesame oil can be grounding. You could massage your feet; the sleep guidance also mentions the head. [P2] [P4] [P1]
- **Optional:** Have warm milk with Ashwagandha if that suits you. [P2]
- **Around 9:30–10:00 PM:** Go to bed at a consistent time. Keep wake time steady, around 5:30–6:00 AM, and avoid naps if they interfere with nighttime sleep. The Vata sleep guidance recommends 8–9 hours. [P5]

Autumn/early winter guidance also favors staying warm and keeping a consistent routine. [P6] If you can, make **9:30 PM** your target bedtime so you have a better chance of getting enough sleep before your usual wake time.

**Sources**
- `sleep-protocols.md`
- `Vata_Dosha.md`
- `Tridosha_Principle_Comprehensive_Guide.md`
- `NEORISHI_KNOWLEDGE_BASE_V4.md`
- `NEORISHI_KNOWLEDGE_BASE_V3.md`
- `Dinacharya.md`
- `VBR_Engine.md`
- `varsha.md`
- `dosha_dushya_framework.md`
- `ritucharya-lifestyle.md`
```
