# rgeo - idea to reusable geometry

## Projektziel

Die Werkzeuge aus `261121-Brillenfassung-MVP` als eigenstaendiges, abstraktes
Open-Source-Paket, damit sie in anderen Projekten wiederverwendbar sind und
nicht in der Brillen-Fachlogik stecken bleiben.

Repo: https://github.com/gbechtold/reusable-geometry (MIT, **derzeit privat**)

## Stand 22.11.2026

Version 0.1.0 steht: 10 Module, 54 Tests gruen, CI gruen auf Python 3.11 und
3.12, zwei lauffaehige Beispiele. Kein fremdes Bildmaterial im Repo: das
Beispiel erzeugt seine Konturen selbst, und `roundtrip.py` rendert das Modell,
zeichnet den Render ab und misst beides gegeneinander.

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

1. **Veroeffentlichung noch nicht entschieden.** Privat angelegt, Register-
   Eintrag `7261feb013d6`. Oeffentlich waere Stufe 2 nach AGENTS.md Paragraf 3
   und braucht eine Freigabe.
2. **Noch nicht auf PyPI.** `pyproject.toml` ist fertig, der Name `rgeo` auf
   PyPI nicht geprueft.
3. **Veraenderliche Wandstaerke schliesst getrimmte Rueckdeckel aus.** Mit mehr
   als einem Loch wird abgelehnt. Eine Freiformflaeche durch die hinteren Wires
   waere der Ausweg, ist aber ein eigenes Thema.
4. **Nur die Flaechen, die gebraucht wurden**: Ebene, Zylinder, Kugel, Torus.
   Kegel und Freiform fehlen.
5. **Die Brille zieht noch nicht auf rgeo um.** `261121-Brillenfassung-MVP`
   hat weiter seine eigene Kopie der Module.

## Arbeitsweise

```
.venv/bin/python -m pytest tests          # 54 Tests
.venv/bin/python examples/eyewear/front.py
.venv/bin/python examples/eyewear/roundtrip.py
```

Beide Beispiele enden bei einer fehlgeschlagenen Pruefung mit Exit 1 und
laufen so in der CI.

Regeln fuer Beitraege stehen in `CONTRIBUTING.md`, die gemessenen Befunde
hinter jeder Entwurfsentscheidung in `docs/WHY.md`. Beides ist Englisch nach
AGENTS.md Paragraf 1 (Repo-Dateien).
