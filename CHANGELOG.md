# WolfLink local

## 0.3.0b1 – 19. Oktober 2026

Erstes festes Paket für die externe Testrunde. Kein zusätzlicher Live-Hardwaretest auf anderen Anlagen erfolgt.

- Ausschließlich lokale ISM7-Anbindung unter `custom_components/wolflink_local`; keine WOLF-Cloud-Anmeldung erforderlich.
- Bedienung, eigenes Anlagenschema, tabellarische Heizung/Warmwasser und verfügbare Energiestatistik enthalten.
- Geräteinformationen in der Übersicht: Anlagenstatus links, Heizgerät und Bedienmodul rechts.
- Optionale Raumtemperatur in Bedienung, Übersicht und Heizung; ohne gültigen Messwert ausgeblendet.
- Adaptive Darstellung für Desktop, Tablet und Smartphone; Hinweise in der Reiterzeile.
- Lokale Wiederanmeldung mit gespeichertem Passwort; bestehende Read-only-/Schreibfreigabe bleibt erhalten.
- Installationsanleitung, Beschreibung, Änderungsliste und Testhinweise im ZIP-Hauptverzeichnis und im Integrationsordner.
- Gegenüber 0.3.0.dev3 keine Änderungen an der Heizungssteuerung; Versionsstand und Dokumentation für die Testrunde festgeschrieben.

Bekannte Grenzen: primär CGB-2/CGW-2 mit einem BM-2 geprüft. Andere Modelle, optionale Raumfühler und frische Installationen müssen durch Tester bestätigt werden. Energiesummen sind Anlagenwerte, keine unabhängige Messung. Zeitfensterende 24:00 wird derzeit abgewiesen. Party-/Urlaubsaktivierung wurde nicht an der laufenden Entwicklungsanlage ausgelöst.

## 0.3.0.dev3

- Optionale Raumtemperatur in Bedienung, Übersicht und Heizung; ohne gültigen Messwert automatisch ausgeblendet.

- Geräteinformationen unter dem Anlagenstatus in die Übersicht integriert; separaten Reiter entfernt.

- Ansichtstitel auf „Wolflink local“ geändert.
- Leeren Abschnitt der früheren Überschrift entfernt; Reiter beginnen näher unter der HA-Kopfzeile.

## 0.3.0.dev2

- Eigenständige lokale Integration unter `custom_components/wolflink_local`.
- Domain, Dienste, Frontend-Pfade und Paketstruktur auf `wolflink_local` umgestellt.
- Cloud-Transport, Cloud-Diagnosewerkzeuge und alte Entwicklungsdateien entfernt.
- Lokale Modul-Weboberfläche als Geräte-Link.
- Bedienung, Zeitprogramme, Statusanzeige und adaptive Darstellung beibehalten.
