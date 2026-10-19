# WolfLink local – Funktionen und Grenzen


## Oberfläche

- Bedienung mit Temperaturreglern, Programmwahl und 1x Warmwasser.
- Anlagenübersicht als eigenes vereinfachtes Funktionsschema mit verfügbaren Livewerten.
- Tabellen für Heizung und Warmwasser.
- Zeitprogramme 1–3 mit Wochenübersicht, Tageseditor und Kopieren eines Tages auf ausgewählte Tage oder die ganze Woche.
- Kompakte Party- und Urlaubsdialoge.
- Energiestatistik mit Bereichsaufteilung, Tages- und Jahresvergleich bei verfügbaren Werten.
- Geräteinformationen bei verfügbaren Daten.

Alles wird aus dem Integrationsordner bereitgestellt. Die automatische Seite ordnet Entitäten je Gerät zu und verändert keine persönlichen Dashboards.

## Rückmeldungen und Zeiten

Blau: Schreibauftrag wird bearbeitet. Gelb: übertragen, noch nicht bestätigt; am Temperaturregler auch lokaler Entwurf vor dem Senden. Grün: passender Wert zurückgelesen oder aktueller Anlagenwert. Rot: Fehler oder nicht bestätigt. Grau: nicht verfügbar. Grün bedeutet nicht automatisch eingeschaltet.



## Energieangaben richtig verstehen

WOLF beschreibt für CGB-2 mit BM-2 berechnete Gasverbrauchs- und Wärmemengenwerte für Tage und Jahre. Sie werden aus Brennerlaufzeit und Gerätedaten ermittelt und sind keine unabhängigen Zählermessungen. Kalenderjahre laufen vom 1. Januar bis 31. Dezember. Die Bereichssummen Heizung/Warmwasser gelten seit Beginn der Aufzeichnung, nicht zwingend seit der ersten Inbetriebnahme.

Die gelieferten Tages- und Jahreswerte der Entwicklungsanlage wurden noch nicht mit der Anzeige am BM-2 gegengeprüft; insbesondere ein auffällig niedriger aktueller Jahreswert ist ungeklärt. Keine Eignung als Abrechnungsgrundlage behauptet. Fehlende Daten werden nicht als Null dargestellt.

Quelle: WOLF CGB-2 Betriebsanleitung 3063421_202311, Kapitel 25, Seite 53:
https://static1.wolfeu.website.svc.wolf.eu/public/assets/editors/de-de/professionals/wissensmanagement/campus/seminarunterlagen/05-cgb-2-bis-24kw/betriebsanleitung-cgb-2-bis-24kw_3063421_202311_web.pdf

## Bekannte Grenzen

- Lokal zunächst CGB-2-Familie mit einem BM-2 und einem Wärmeerzeuger; kein allgemeiner Nachweis für alle WOLF-Anlagen.
- ISM7: nur eine gleichzeitige lokale Verbindung.
- Lokal maximal drei editierbare Zeitfenster pro Tag. Ende 24:00 wird wegen einer bekannten Encodergrenze abgewiesen.
- Party-/Urlaubsaktivierung ist implementiert und automatisiert simuliert geprüft; an der laufenden Entwicklungsheizung wurden nur die Zeitfelder gelesen, nicht die Modi aktiviert.
- Ein lokales Zeitfenster wurde live geändert, unabhängig zurückgelesen und bytegenau wiederhergestellt.
- Optionale Raumtemperatur bleibt unterstützt; ohne Fühler kein Ersatzwert.
- Grafisches Schema ist auf CGB-2 ausgerichtet; andere Hydrauliken können abweichen.

## Lizenz und Herkunft

Unabhängiges Projekt, keine offizielle WOLF-App. GPL-3.0 für das kombinierte Paket, bestehende Apache-2.0-Hinweise bleiben erhalten. Die Bilddateien dieses Pakets sind eigene Projektgrafiken; WOLF wird als Hersteller kompatibler Geräte genannt. Siehe LICENSE, NOTICE, WOLF-SCHEMA-QUELLE.json sowie local/SOURCE.json und local/LICENSE.GPL-3.0.

## Tablet im Querformat

Bei 900–1400 Pixeln Breite und bis zu 1100 Pixeln Höhe wird im Querformat eine kompakte Bedienansicht verwendet: kleinere Regler, zweispaltige Statuszeilen sowie weniger Abstand im Kopfbereich. Alle Werte und Dialogaktionen bleiben zugänglich. Im Browser mit 1024 × 680 und 1366 × 930 Pixeln geprüft; ein echter iPad-/Safari-Test steht noch aus. Für mehr Platz die HA-Seitenleiste einklappen. Browserleisten, Zoom, geöffnete Hinweise und Dialoge können weiterhin Scrollen erforderlich machen.

Auch Übersicht, Heizung, Warmwasser, Energiestatistik und Geräteinformationen nutzen das kompakte Querformat: Schema und Status nebeneinander, mehrspaltige Tabellenabschnitte, kompaktere Diagramme und aufklappbare Energiehinweise. Alle Reiter wurden im Browser bei 1024 × 680 und 1366 × 930 Pixeln auf sichtbare Gesamthöhe geprüft. Ein echter Safari-Hardwaretest bleibt erforderlich. Erweiterte Hinweise und Dialoge können scrollen.

## Technisches Schema ab 17.10.2026

Die Anlagenübersicht verwendet das abgestimmte eigene technische Schema mit sichtbaren Rohrwegen, Richtungspfeilen, Abgasrohr, Wasserhahn und Außentemperatur in einer Wolke. Der Brenner verwendet das Apache-2.0-Icon mdi-fire; Quelle und Lizenzen liegen unter brand/. Im kompakten Tablet-Querformat nutzt die Grafik die gesamte Breite. Die zusätzliche Statustabelle ist über „Anlagenstatus anzeigen“ aufklappbar. Bei geöffnetem Status kann Scrollen erforderlich sein. Die aktuelle Frontend-Datei wurde in einer separaten Layoutprüfung mit Beispieldaten bei 1024 × 680 und 1366 × 930 geprüft. Nach dem Update die Browserseite vollständig neu laden; gespeicherte ältere JavaScript-Versionen können sonst noch die bisherige Grafik anzeigen.

Lokale ISM7-Anbindung mit Live-Messwerten, Betriebsarten, Temperaturen, Zeitprogrammen mit Tageskopie, Party- und Urlaubszeiträumen sowie verfügbaren Energie- und Geräteinformationen. Angezeigt wird nur, was die Anlage unterstützt.

Nach dem Schreiben: sofortige Rücklesung und bei Bedarf weitere Versuche nach 1, 2, 3 und 5 Sekunden. Gelb bleibt bis zum tatsächlichen Abgleich bestehen. Weitere Prüfungen können bis zu zehn Minuten laufen. Schreibbefehle werden nicht automatisch wiederholt. Regulärer Abfragetakt 60 Sekunden, einstellbar von 15 bis 900 Sekunden; Keepalive alle 25 Sekunden. Read-only ist bei neuen Einträgen aktiv. Bestehende Schreibfreigaben bleiben bei Wiederanmeldung erhalten.

## Optionaler Raumfühler

Ein von der Anlage gelieferter Raumtemperatur-Messwert wird in Bedienung, Übersicht und Heizung angezeigt. Ohne gültigen numerischen Messwert bleibt die Anzeige ausgeblendet. Es wird weder die Tag-Solltemperatur noch ein Ersatzwert als gemessene Raumtemperatur verwendet. Ein erstmals angeschlossener Sensor wird bei erneuter Erkennung der Integration berücksichtigt.
