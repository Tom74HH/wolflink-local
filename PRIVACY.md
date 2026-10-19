# Datenschutz und sichere Fehlermeldungen

WolfLink local verbindet Home Assistant über das lokale Netzwerk mit dem ISM7. Für die Verbindung wird kein WOLF-Cloud-Konto benötigt. Die Integration enthält keine eigene Telemetrie oder automatische Übertragung von Heizungsdaten an GitHub.

## Was lokal gespeichert wird

Home Assistant speichert die Moduladresse, das Modulpasswort sowie Geräteidentität und Zertifikatbindung in seiner eigenen Konfiguration. Messwerte können abhängig von der HA-Konfiguration in Verlauf und Recorder gespeichert werden. Diese persönlichen Dateien gehören nicht in dieses Repository.

## Öffentliche Issues und Bilder

GitHub-Issues und Anhänge sind in einem öffentlichen Repository öffentlich sichtbar. Bitte keine Passwörter, Tokens, private Schlüssel, vollständigen HA-Konfigurationen, unbereinigten Protokolle oder Datenbankdateien hochladen. Entferne private Adressen, Gerätenummern, Hostnamen, Namen und E-Mail-Adressen aus Bildern und Auszügen. Modell, Firmware, Integrationsversion und eine kurze Fehlerbeschreibung reichen für den Anfang.

## Gemeinsame Protokollressourcen

Die Dateien `custom_components/wolflink_local/local/client-cert.pem` und `client-key.pem` stammen aus den öffentlichen gemeinsamen ISM7-Protokollressourcen des in `local/SOURCE.json` genannten Projekts. Sie sind keine Zugangsdaten der Entwicklungsanlage. Das persönliche Modulpasswort und die installierte Gerätebindung werden nicht mitgeliefert.

## Andere Dienste

Die Datenschutzeinstellungen des verwendeten Home Assistant und dessen weiterer Integrationen gelten unabhängig von diesem Projekt. Das Öffnen externer Dokumentations- oder Projektlinks ruft den jeweiligen Anbieter auf.
