# rgeo - idea to reusable geometry

## Projektziel

Die Werkzeuge aus `261121-Brillenfassung-MVP` als eigenstaendiges, abstraktes
Open-Source-Paket, damit sie in anderen Projekten wiederverwendbar sind und
nicht in der Brillen-Fachlogik stecken bleiben.

Repo: https://github.com/gbechtold/reusable-geometry (MIT, oeffentlich seit 22.11.2026)

## Stand 22.11.2026

Version 0.2.0: 12 Module, 77 Tests gruen, CI gruen auf Python 3.11 und 3.12,
drei lauffaehige Beispiele. Seit 22.11.2026 dazu eine Feature-Hierarchie mit
klickbarem Scharnier und Buegeln. Kein fremdes Bildmaterial im Repo: das
Beispiel erzeugt seine Konturen selbst, und `roundtrip.py` rendert das Modell,
zeichnet den Render ab und misst beides gegeneinander.

## Die Feature-Hierarchie

```
Feature                      benannt, prueft sich selbst
|-- ProfileFeature           aendert eine Wand. Kein Koerper, kein Boolean.
|                            Groove, EdgeBreak, Boss
+-- BodyFeature              bringt Koerper mit
        +-- MechanicalFeature    zwei Teile, die passen muessen; das Spiel
                                 wird GEMESSEN, nicht behauptet. ClipHinge
```

`ClipHinge` ist das Steckscharnier: Gabel am Gestell, Querstift am Buegel. Die
Rastgeometrie (Einfuehrung, Engstelle, Mulde) ist die **Form des Schlitzes**,
kein nachtraeglicher Schnitt. `measured_gap()` misst den Abstand zwischen
beiden Haelften (0,144 mm bei 0,15 mm Nennspiel).

Die Buegel zeigen Vererbung, die sich lohnt: `Temple` macht Mittellinie,
Querschnitt, Verjuengung und Pruefungen, die Unterklassen ueberschreiben nur
`drop()`. `SkullTemple`, `LibraryTemple`, `CableTemple`.

## Die drei Kernideen

1. **Parameter tragen ihre Herkunft.** `Measured` / `Fitted` / `Assumed`
   verhalten sich wie `float`, wissen aber, woher sie kommen. `p.table()` gibt
   eine Markdown-Tabelle, `p.assumptions()` die Annahmen.
2. **Koerper werden als Waende beschrieben, nicht herausgeschnitten.** Fase,
   Nut, Absatz und veraenderliche Wandstaerke sind Versaetze im Wandprofil.
   Dadurch gibt es im Grundkoerper keine einzige Boolean-Operation.
3. **Der Vergleich passt die Kamera an, nie die Geometrie**, und meldet
   Millimeter neben der Ueberdeckung.

## Was offen ist

1. **Noch nicht auf PyPI.** `pyproject.toml` ist fertig, der Name `rgeo` auf
   PyPI nicht geprueft.
2. **Veraenderliche Wandstaerke schliesst getrimmte Rueckdeckel aus.** Mit mehr
   als einem Loch wird abgelehnt. Deshalb traegt `ClipHinge` einen Flansch,
   statt die Front einen Boss zu bekommen. Eine Freiformflaeche durch die
   hinteren Wires waere der Ausweg, ist aber ein eigenes Thema.
3. **Das Scharnier ist nicht gedruckt und nicht gefedert gerechnet.** Die
   Rastueberdeckung von 0,28 mm ist plausibel, aber ungeprueft: ob PA12 bei
   dieser Backenstaerke so weit federt, ohne zu brechen, sagt erst ein Druck.
4. **Nur die Flaechen, die gebraucht wurden**: Ebene, Zylinder, Kugel, Torus.
   Kegel und Freiform fehlen.
5. **Die Brille zieht noch nicht auf rgeo um.** `261121-Brillenfassung-MVP`
   hat weiter seine eigene Kopie der Module.

## Arbeitsweise

```
.venv/bin/python -m pytest tests          # 77 Tests
.venv/bin/python examples/eyewear/front.py
.venv/bin/python examples/eyewear/roundtrip.py
.venv/bin/python examples/eyewear/glasses.py     # Front, 2 Scharniere, 2 Buegel
```

Beide Beispiele enden bei einer fehlgeschlagenen Pruefung mit Exit 1 und
laufen so in der CI.

Regeln fuer Beitraege stehen in `CONTRIBUTING.md`, die gemessenen Befunde
hinter jeder Entwurfsentscheidung in `docs/WHY.md`. Beides ist Englisch nach
AGENTS.md Paragraf 1 (Repo-Dateien).
