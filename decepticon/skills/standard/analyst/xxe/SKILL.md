---
name: xxe
description: Hunt XML External Entity flaws in parsers and validate file read / SSRF impact with strict negative controls.
---

# XXE Playbook

## Find parser sinks
- Java: `DocumentBuilderFactory`, `SAXParserFactory`, `XMLInputFactory`
- Python: `lxml.etree`, `xml.dom.minidom`, `xml.sax`
- .NET: `XmlDocument`, `XDocument`, `XmlReader`

## Dangerous defaults
- DTD enabled
- External entities enabled
- Network/file entity resolution enabled

## Payloads
- File read: entity to `file:///etc/passwd`
- SSRF: entity to internal URL (metadata service, localhost admin)

## Validation
- Positive: parser output contains file content or internal response markers.
- Negative: same XML without entity expansion must not leak content.
