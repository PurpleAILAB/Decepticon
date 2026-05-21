# Red Team Reconnaissance Methodology

> Decepticon Recon Agent의 도메인 지식 기반 문서.
> 프레임워크 참조: MITRE ATT&CK TA0043, OWASP WSTG, PTES, NIST SP 800-115

---

## 1. Recon 프레임워크 매핑

### 1.1 MITRE ATT&CK Reconnaissance (TA0043)

| Technique ID | Name | Decepticon 적용 |
|---|---|---|
| T1595 | Active Scanning | nmap, naabu, masscan |
| T1595.001 | Scanning IP Blocks | nmap -sS on target ranges |
| T1595.002 | Vulnerability Scanning | nuclei, nmap NSE scripts |
| T1595.003 | Wordlist Scanning | ffuf, gobuster, feroxbuster |
| T1592 | Gather Victim Host Information | OS detection, service versioning |
| T1589 | Gather Victim Identity Information | theHarvester, CrossLinked |
| T1590 | Gather Victim Network Information | DNS, WHOIS, ASN mapping |
| T1591 | Gather Victim Org Information | LinkedIn, public filings |
| T1593 | Search Open Websites/Domains | Google dorking, GitHub search |
| T1594 | Search Victim-Owned Websites | spider, JS analysis |
| T1596 | Search Open Technical Databases | Shodan, Censys, crt.sh |
| T1597 | Search Closed Sources | threat intel feeds |
| T1598 | Phishing for Information | (out of scope for recon agent) |

### 1.2 OWASP WSTG Information Gathering

| Test ID | Name | 기법 |
|---|---|---|
| WSTG-INFO-01 | Search Engine Discovery | Google Dorking, cached pages |
| WSTG-INFO-02 | Fingerprint Web Server | Banner grabbing, HTTP headers |
| WSTG-INFO-03 | Review Webserver Metafiles | robots.txt, sitemap.xml, security.txt |
| WSTG-INFO-04 | Enumerate Applications | Virtual hosts, non-standard ports |
| WSTG-INFO-05 | Review Webpage Content | Comments, metadata, hidden fields, JS |
| WSTG-INFO-06 | Identify Entry Points | URL params, HTTP headers, POST bodies |
| WSTG-INFO-07 | Map Execution Paths | Application flow, state transitions |
| WSTG-INFO-08 | Fingerprint Framework | Framework headers, cookies, directories |
| WSTG-INFO-09 | Fingerprint Web Application | CMS identification, version detection |
| WSTG-INFO-10 | Map Application Architecture | Load balancers, WAFs, reverse proxies |
| WSTG-APIT-01 | API Reconnaissance | OpenAPI/Swagger discovery, endpoint enum |

### 1.3 PTES & NIST SP 800-115

**PTES Phase 2 (Intelligence Gathering)**:
- OSINT → Active Footprinting → Target Validation → Port Scanning → Data Correlation

**NIST 5-Phase Model**:
1. Planning → 2. Information Gathering (Recon) → 3. Vulnerability Analysis → 4. Exploitation → 5. Post-Testing

---

## 2. Passive Recon 기법 상세

### 2.1 OSINT 프레임워크 및 도구

| Tool | 역할 | 데이터 소스 |
|---|---|---|
| **theHarvester** | 이메일, 서브도메인, IP 수집 | 30+ 소스 (Google, Bing, PGP) |
| **Amass** | DNS 열거 + OSINT 매핑 | Passive DNS + active resolution |
| **SpiderFoot** | 자동 OSINT 통합 | 200+ 데이터 소스 |
| **Recon-ng** | 모듈러 정찰 프레임워크 | Metasploit 스타일 인터페이스 |
| **Maltego** | 시각적 링크 분석 | 58+ transforms |

**권장 패시브 워크플로우**:
```
theHarvester (이메일/도메인)
  → Amass + crt.sh (서브도메인)
    → SpiderFoot (풀 패시브 스캔)
      → Shodan/Censys (노출 서비스)
        → Google Dorks + waybackurls (최종 스윕)
```

### 2.2 DNS 인텔리전스

**기본 DNS Recon**:
```bash
dig example.com ANY +noall +answer
dig example.com A AAAA MX NS TXT CNAME SOA +short
dig -x <IP> +short                                    # Reverse DNS
dig @ns1.example.com example.com AXFR                 # Zone transfer
```

**패시브 DNS 데이터베이스**:

| 서비스 | 용도 |
|---|---|
| PassiveTotal (RiskIQ) | 위협 분석, 패시브 DNS 이력 |
| SecurityTrails | 히스토리컬 DNS 데이터, 도메인 인텔리전스 |
| Robtex | 도메인/DNS/IP/Route/AS 관계 매핑 |
| DNSdumpster | DNS 정찰 및 매핑 |

**DNS 분석 패턴**:
- **MX 레코드**: 이메일 인프라 식별 (Google Workspace, M365, 자체 호스팅)
- **TXT 레코드**: SPF, DKIM, DMARC 설정 + 서비스 인증 토큰 노출
- **CNAME 체인**: CDN, 서드파티 통합, 서브도메인 테이크오버 후보
- **SOA 레코드**: DNS 관리자 연락처, 변경 빈도 지표
- **NS 위임**: DNS 호스팅 제공자 (Cloudflare, Route53 등)

### 2.3 서브도메인 열거

**권장 도구 스택**:

| Tool | 유형 | 핵심 기능 |
|---|---|---|
| **Subfinder** | Passive | 40+ API, Go 기반, 빠름 |
| **Amass** | Hybrid | 가장 포괄적, 그래프 DB |
| **ShuffleDNS** | Active | MassDNS 래퍼, 와일드카드 필터링 |
| **puredns** | Active | DNS 리졸빙 + 와일드카드 탐지 |
| **BBOT** | Hybrid | 차세대 복합 스캐너 |

**중요**: 서브도메인 리스트를 httpx로 보내기 전에 반드시 puredns/shuffledns로 DNS 리졸빙하여 유효하지 않은 항목 필터링.

```bash
subfinder -d example.com -all -o subs_passive.txt
amass enum -passive -d example.com -o subs_amass.txt
cat subs_*.txt | sort -u > all_subs.txt
puredns resolve all_subs.txt -r resolvers.txt -w resolved.txt
cat resolved.txt | httpx -title -status-code -tech-detect -o alive_hosts.txt
```

### 2.4 Certificate Transparency (CT)

```bash
curl -s "https://crt.sh/?q=%25.example.com&output=json" | \
    python3 -c "import sys,json; [print(x['name_value']) for x in json.load(sys.stdin)]" | sort -u
```

**가치**:
- DNS 열거로 발견 못한 서브도메인 노출
- 폐지된 인증서도 과거 인프라 노출
- 와일드카드 인증서 → 광범위한 서브도메인 사용 지표
- 실시간 모니터링 가능 (Certstream)

### 2.5 인터넷 스캐닝 데이터베이스

| 엔진 | 강점 | 주요 필터 |
|---|---|---|
| **Shodan** | 가장 인기, 디바이스 중심, CLI | `port:`, `org:`, `vuln:`, `product:` |
| **Censys** | 가장 정확(92%), 전체 65K 포트 | 호스트/인증서 검색 |
| **ZoomEye** | 중국 엔진, 웹+디바이스 결합 | 컴포넌트 검색 |

```bash
# Shodan
shodan search "org:TargetCorp port:443"
shodan host 1.2.3.4

# Censys
censys search "services.http.response.headers.server: nginx AND autonomous_system.name: TargetCorp"
```

### 2.6 웹 아카이브 분석

| Tool | 소스 |
|---|---|
| **waybackurls** | Wayback Machine |
| **gau** | Wayback + AlienVault OTX + CommonCrawl + URLScan |
| **waymore** | Wayback + CommonCrawl + URLScan + VirusTotal |

```bash
echo "example.com" | waybackurls > urls.txt
echo "example.com" | gau --threads 5 > gau_urls.txt
```

### 2.7 GitHub/GitLab 시크릿 스캐닝

| Tool | 핵심 기능 |
|---|---|
| **TruffleHog** | 700+ 자격증명 탐지기, API 검증, Git/S3/Docker 스캔 |
| **Gitleaks** | 경량, 빠름, Git 리포지토리 집중 |
| **GitGuardian** | SaaS 시크릿 스캐닝 + CI/CD 통합 |

```bash
trufflehog github --org=targetorg
gitleaks detect -s /path/to/repo -v
```

### 2.8 클라우드 인프라 핑거프린팅

| Tool | 대상 |
|---|---|
| **CloudEnum** | AWS S3 + Azure Blob + GCP 버킷 동시 열거 |
| **lazys3** | S3 버킷 브루트포스 |
| **S3Scanner** | S3 버킷 스캔, 권한 확인 |
| **GCPBucketBrute** | GCP 버킷 열거 + 권한 상승 확인 |
| **CloudFox** | AWS/Azure/GCP 상황 인식 자동화 |

### 2.9 ASN/BGP 인텔리전스

```bash
whois -h whois.radb.net -- '-i origin AS12345'
dig TXT AS12345.asn.cymru.com +short
```

**핵심 인텔리전스**: 대상 IP 범위 식별, 네트워크 프로바이더/피어링 관계, 자회사 네트워크 매핑.

### 2.10 소셜/직원 OSINT

| Tool | 용도 |
|---|---|
| **CrossLinked** | LinkedIn 직원 이름 열거 |
| **Hunter.io** | 이메일 패턴 식별 + 검증 |
| **Sherlock** | 300+ 소셜 플랫폼 사용자명 열거 |

---

## 3. Active Recon 기법 상세

### 3.1 Nmap 스캔 전략 (단계적 확대)

```bash
# Phase 1: 타겟 포트 SYN 스캔 (최소 노이즈)
nmap -sS -p 22,80,443,8080,8443 <TARGET> -T2 -oN scan_targeted.txt

# Phase 2: Top 1000 포트 + 서비스 탐지
nmap -sS -sV --top-ports 1000 <TARGET> -T3 -oN scan_top1000.txt

# Phase 3: NSE 스크립트 열거
nmap -sC -sV -p <DISCOVERED_PORTS> <TARGET> -oN scan_scripts.txt

# Phase 4: UDP 핵심 서비스
nmap -sU -p 53,161,123,500 <TARGET> -oN scan_udp.txt

# Phase 5: 전체 포트 스캔 (필요 시에만)
nmap -sS -p- <TARGET> -T3 --min-rate 1000 -oN scan_allports.txt
```

### 3.2 NSE 스크립트 카테고리

| 카테고리 | 스크립트 예시 | 용도 |
|---|---|---|
| HTTP | `http-title`, `http-enum`, `http-methods` | 웹 서비스 핑거프린팅 |
| SSL/TLS | `ssl-enum-ciphers`, `ssl-cert`, `ssl-heartbleed` | 암호화 분석 |
| SSH | `ssh2-enum-algos`, `ssh-hostkey` | SSH 설정 평가 |
| DNS | `dns-nsid`, `dns-recursion`, `dns-zone-transfer` | DNS 서비스 분석 |
| SMTP | `smtp-commands`, `smtp-enum-users` | 메일 서버 열거 |
| SMB | `smb-os-discovery`, `smb-enum-shares` | Windows 열거 |
| Vuln | `vulners`, `vulscan` | CVE 매핑 |

### 3.3 웹 애플리케이션 핑거프린팅

| Tool | 핵심 기능 |
|---|---|
| **httpx** | 서브도메인 프로빙, 타이틀/상태/기술 추출 |
| **Nuclei** | 10,000+ 템플릿, CVE/미스컨피그 탐지 |
| **WhatWeb** | 1,800+ 플러그인, 기술 스택 식별 |

```bash
cat subdomains.txt | httpx -title -status-code -tech-detect -o alive.txt
nuclei -l alive.txt -t cves/ -t misconfiguration/ -o vulns.txt
```

### 3.4 API 엔드포인트 디스커버리

**패시브**:
- `/swagger.json`, `/openapi.json`, `/api-docs`, `/graphql` 확인
- Google Dorking: `site:example.com inurl:api`
- Wayback Machine으로 deprecated API 엔드포인트 확인

**액티브**:

| Tool | 용도 |
|---|---|
| **KiteRunner** | API 경로 브루트포스 |
| **ffuf** | 범용 API 퍼징 |
| **Arjun** | 히든 HTTP 파라미터 발견 |

```bash
kr scan https://api.example.com -w routes-large.kite
ffuf -u https://api.example.com/FUZZ -w api-wordlist.txt -mc 200,201,301,401,403
```

### 3.5 디렉토리/경로 브루트포싱

| Tool | 언어 | 특장점 |
|---|---|---|
| **feroxbuster** | Rust | 가장 빠름, 자동 재귀 |
| **ffuf** | Go | 가장 유연 (HTTP 요청 어디든 퍼징) |
| **gobuster** | Go | 경량, dir/dns/vhost/s3 모드 |

```bash
feroxbuster -u https://example.com -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt
ffuf -u https://example.com/FUZZ -w wordlist.txt -mc 200,301,302,403 -fc 404
```

### 3.6 JavaScript 분석

| Tool | 용도 |
|---|---|
| **LinkFinder** | JS 파일에서 엔드포인트/파라미터 추출 |
| **SecretFinder** | JS에서 API 키, 토큰, 자격증명 발견 |
| **Gospider** | JS 파일 발견용 웹 스파이더 |

### 3.7 WAF 탐지

```bash
wafw00f https://example.com -a
```

### 3.8 Virtual Host 열거

```bash
gobuster vhost -u http://target.com -w vhosts-wordlist.txt --append-domain
ffuf -w namelist.txt -u http://10.x.x.x -H "HOST: FUZZ.target.com" -fs <default_size>
```

---

## 4. OPSEC 원칙

### 4.1 스캔 탐지 회피

| 기법 | Nmap 플래그 | 설명 |
|---|---|---|
| 타이밍 제어 | `-T0` ~ `-T5` | T0/T1: 대부분 IDS 회피 |
| 스캔 딜레이 | `--scan-delay 1s` | 패킷 간 딜레이 |
| 단편화 | `-f` | 패킷 검사 우회 |
| 디코이 | `-D RND:10` | 10개 랜덤 디코이 IP 혼합 |
| 소스 포트 | `--source-port 53` | 신뢰 포트(DNS) 사용 |
| 데이터 길이 | `--data-length 25` | 시그니처 탐지 회피 |

**IDS 임계값 참고**: Snort 기본 = 초당 15+ 포트 스캔 시 알림. T1 + 단편화 + 데이터 패딩 = 거의 탐지 불가 (매우 느림).

### 4.2 Rules of Engagement (ROE)

ROE에 반드시 정의해야 할 항목:
- **범위**: 타겟 시스템, 네트워크, 애플리케이션 정확히 식별
- **기간**: 시작/종료 일시
- **허용 기법**: 허용되는 공격 벡터, 도구, 방법론
- **금지 행위**: DDoS, 동의 없는 소셜 엔지니어링, 물리적 접근
- **데이터 처리**: PII, PHI, PCI 데이터 처리 방법
- **커뮤니케이션**: 비상 연락처, 인시던트 에스컬레이션
- **디컨플릭션**: 테스트 활동 vs 실제 공격 구분 방법

---

## 5. 자동화 파이프라인

### 5.1 reconFTW 통합 워크플로우

```
서브도메인 열거 (passive + active + permutation + recursive)
  → 웹 프로빙 (httpx, 스크린샷)
    → 포트 스캐닝 (nmap, naabu, masscan)
      → 웹 취약점 스캐닝 (nuclei, XSS, SSRF, SQLi)
        → OSINT 수집
          → 디렉토리 퍼징
            → 파라미터 발견
              → JavaScript 분석
```

### 5.2 버그바운티 커뮤니티 워크플로우 (TBHM)

```
Subfinder/Amass → puredns → httpx → nuclei → 수동 분석
     |                                    |
     +→ gau/waybackurls → param mining ---+
     |                                    |
     +→ port scan (naabu) → service enum -+
```

---

## 6. 2025-2026 트렌드

### 6.1 AI 기반 정찰
- 2025년이 AI 오케스트레이션 공격의 변곡점
- AI 에이전트가 네트워크 매핑, 고가치 데이터 저장소 식별, 섀도 IT 탐지를 **몇 분** 내 수행
- 기존 1주일 소요 공격 → 몇 시간/분으로 단축
- CensysGPT: 자연어 → Censys 쿼리 변환

### 6.2 클라우드 네이티브 공격 표면
- 새 Kubernetes 클러스터 배포 후 **18분 이내** 악의적 정찰 시작
- 클라우드 미스컨피그 + 아이덴티티 보안 갭이 주요 리스크
- 포인트 인 타임 → 지속적 스캐닝 전환 필수

### 6.3 공급망 정찰
- 공급망 침해 40% 증가 (2년 대비)
- 전체 침해의 1/3이 서드파티 벤더에서 발생
- OAuth 토큰 탈취로 익스플로잇/피싱 없이 접근
- 새 정찰 대상: SaaS-to-SaaS 통합, CI/CD 파이프라인, 패키지 매니저

### 6.4 API-First 공격 표면
- 65% 조직이 GenAI 통합으로 API 공격 표면 증가 인식
- 섀도 API (미문서화, 잊혀진) 위험 증가
- API 보안 테스트는 지속적/자동화 필수

---

## 7. Decepticon 에이전트용 도구 분류

### Passive Recon Tools
| 카테고리 | 도구 |
|---|---|
| OSINT 프레임워크 | Maltego, SpiderFoot, Recon-ng |
| 이메일/도메인 수집 | theHarvester, Hunter.io, CrossLinked |
| 서브도메인 열거 | Subfinder, Amass (passive), Chaos |
| DNS 인텔리전스 | dig, whois, PassiveTotal, SecurityTrails |
| CT 로그 | crt.sh, Certstream |
| 인터넷 스캐닝 | Shodan, Censys, ZoomEye |
| 웹 아카이브 | waybackurls, gau, waymore |
| 시크릿 스캐닝 | TruffleHog, Gitleaks |
| 소셜/직원 OSINT | CrossLinked, Sherlock |
| 클라우드 열거 | CloudEnum, lazys3, GCPBucketBrute |
| ASN/BGP | bgp.he.net, BGP.Tools |

### Active Recon Tools
| 카테고리 | 도구 |
|---|---|
| 포트 스캐닝 | nmap, naabu, masscan |
| 웹 프로빙 | httpx, nuclei, WhatWeb |
| 서브도메인 브루트포스 | ShuffleDNS, puredns, MassDNS |
| 디렉토리 퍼징 | feroxbuster, ffuf, gobuster |
| API 디스커버리 | KiteRunner, Arjun |
| WAF 탐지 | wafw00f |
| JS 분석 | LinkFinder, SecretFinder |
| VHost 디스커버리 | gobuster (vhost), ffuf (Host 헤더) |
| 서비스 열거 | nmap NSE, netcat, curl |
| 클라우드 특화 | CloudBrute, MicroBurst, Prowler |

### 자동화 프레임워크
| Tool | 범위 |
|---|---|
| reconFTW | 풀 자동 recon 파이프라인 (50+ 도구) |
| AutoRecon | 서비스 열거 자동화 |
| Axiom/Ax | 분산 스캐닝 인프라 |
| BBOT | 차세대 하이브리드 recon 스캐너 |
