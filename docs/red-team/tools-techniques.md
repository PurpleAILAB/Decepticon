# Red Team Tools & Techniques — Kill Chain별 상세

> MITRE ATT&CK 전체 킬 체인의 기법/도구 레퍼런스.
> Recon(TA0043)은 [recon-methodology.md](recon-methodology.md) 참조.

---

## 1. Initial Access (TA0001)

### 1.1 피싱 인프라

| 도구 | 역할 | 핵심 기능 |
|------|------|----------|
| **Evilginx2** | MitM 리버스 프록시 | 세션 쿠키 탈취로 MFA 우회, YAML phishlet 기반 |
| **GoPhish** | 캠페인 관리 | 이메일 발송, 랜딩 페이지, 추적, 리포팅 |
| **Modlishka** | MitM 프록시 | 실시간 자격증명/토큰 캡처 |

**인프라 패턴**: NGiNX 리버스 프록시 → Evilginx(토큰 캡처) + GoPhish(캠페인 오케스트레이션)

### 1.2 공급망 (T1195)
- 2020년 이후 **1,300% 증가**, 2025년 첫 5개월 79건
- 63%가 기술 섹터 대상
- 핵심 벡터: 벤더 침해, OAuth 토큰 탈취, 헬프데스크 소셜 엔지니어링

### 1.3 유효한 계정 (T1078)
- 2025 DBIR: **74% 침해가 손상된 ID** 관련
- 자격증명 스터핑, 패스워드 스프레이, 토큰 탈취가 주요 초기 접근 경로

---

## 2. Execution (TA0002)

### 2.1 C2 프레임워크 비교 (2025)

| 프레임워크 | 라이선스 | 언어 | 프로토콜 | 핵심 강점 | 탐지 수준 |
|-----------|---------|------|---------|----------|----------|
| **Sliver** | OSS | Go | mTLS, HTTPS, DNS, WireGuard | 크로스플랫폼, Armory, 멀티플레이어 | 증가 중 |
| **Havoc** | OSS | C/C++ | HTTP(S), SMB | CS 유사 UI, Demon agent | 낮음 |
| **Mythic** | OSS | Go/Python | HTTP, TCP, Slack, custom | 모듈러 에이전트, BOF, 웹 UI | 낮음 |
| **Cobalt Strike** | 상용 | Java/C | HTTP(S), DNS, SMB, TCP | Malleable C2, BOF, 성숙한 생태계 | 높음 |
| **Brute Ratel C4** | 상용 | C/C++ | HTTP(S), DNS, SMB | EDR 회피 설계, sleep 난독화 | 낮음 |
| **Empire** | OSS | Python | HTTP(S), Dropbox, OneDrive | 다중 언어 에이전트, 방대한 모듈 | 중간 |

**2025 트렌드**: OSS(Sliver, Havoc, Mythic)가 Cobalt Strike를 대체 중 — 낮은 탐지율 + 무료.

### 2.2 Beacon Object Files (BOFs)
- 메모리 내 실행 (디스크 미접촉)
- ~3KB 크기 (DLL ~100KB+ 대비)
- Windows Event Log 기반 탐지 우회
- Cobalt Strike, Sliver(Armory), Mythic 지원

### 2.3 PowerShell
- **71%의 Living-off-the-Land 공격**에서 사용 (Picus 2025 Red Report)

---

## 3. Persistence (TA0003)

### 3.1 Top 10 기법 (2025)

| 순위 | 기법 | 설명 |
|-----|------|------|
| 1 | Registry Run Keys | `HKCU/HKLM\...\Run` |
| 2 | Scheduled Tasks | TaskCache 직접 수정 → 이벤트 로그 우회 |
| 3 | Windows Services | 서비스 생성/수정 (SYSTEM 레벨) |
| 4 | WMI Event Subscription | Filter + Consumer + Binding (파일리스) |
| 5 | COM Hijacking | "최고 가치, 최저 노이즈" (SpecterOps 2025) |
| 6 | DLL Side-Loading | 앱 검색 경로에 악성 DLL 배치 |
| 7 | IFEO Injection | Image File Execution Options 디버거 키 |
| 8 | BITS Jobs | Background Intelligent Transfer Service |
| 9 | Startup Folder | 사용자 레벨, 단순하지만 유효 |
| 10 | Winlogon Manipulation | Shell/Userinit 레지스트리 키 |

**도구**: **SharPersist** (Mandiant) — C# 기반 Windows 지속성 자동화

---

## 4. Privilege Escalation (TA0004)

### 4.1 Potato 계열 (SeImpersonatePrivilege → SYSTEM)

| 도구 | 기법 | OS 지원 |
|------|------|--------|
| **PrintSpoofer** | Print Spooler 네임드 파이프 | Win 10/Server 2016-2019 |
| **GodPotato** | DCOM 기반 | Win 8-11, Server 2012-2022 (가장 범용적) |
| **RoguePotato** | DCOM/OXID | 광범위 |
| **EfsPotato** | MS-EFSR | 광범위 |
| **SigmaPotato** | GodPotato 포크 | 확장 OS + .NET 리플렉션 (2024-2025) |

### 4.2 Kerberos 기반

| 기법 | 조건 | 도구 |
|------|------|------|
| **Kerberoasting** | 도메인 사용자면 가능 | Rubeus, Impacket GetUserSPNs.py |
| **AS-REP Roasting** | Pre-auth 비활성 계정 | Rubeus, Impacket GetNPUsers.py |
| 오프라인 크래킹 | — | Hashcat (13100/18200) |

### 4.3 기타 도구
- **SharpUp**: C# PowerUp 포트
- **winPEAS/linPEAS**: 포괄적 privesc 열거
- **BeRoot**: 미스컨피그 기반 privesc 체크

---

## 5. Defense Evasion (TA0005)

### 5.1 AMSI 우회 (2025)
> "AMSI는 사용자 프로세스 공간 내에서 동작하므로 근본적으로 취약"

| 기법 | 설명 | 탐지 수준 |
|------|------|----------|
| 메모리 패칭 | AmsiScanBuffer에 `0xC3` RET 쓰기 | 높음 (시그니처) |
| **하드웨어 브레이크포인트** | CPU 레벨 BP + VEH로 실행 흐름 변경 | 낮음 (메모리 수정 없음) |
| CLR 후킹 | .NET CLR → AMSI 초기화 전 후킹 | 중간 |
| 리플렉션 | .NET 리플렉션으로 AMSI 내부 수정 | 중간 |
| 에러 강제 | AMSI 컨텍스트 손상 → 스캔 실패 | 중간 |

### 5.2 ETW 패칭
- `EtwEventWrite` 패칭으로 로컬 센서 무력화
- ScareCrow: 다수 ETW 시스콜 패칭 + 레지스터 플러시

### 5.3 ScareCrow 프레임워크
- EDR 언후킹: `System32/`의 클린 DLL → 프로세스 메모리의 후킹된 DLL 덮어쓰기
- AES 암호화 셸코드 (페이로드별 키)
- ETW + AMSI 패칭 내장
- 코드 서명 스푸핑 (LimeLighter)
- 사이드로딩 (인젝션 아님)

### 5.4 커스텀 로더 (Nim/Rust/Go)

| 언어 | 장점 | 대표 도구 |
|------|------|----------|
| **Nim** | 적은 탐지 룰, C/C++ 컴파일 | OffensiveNim, NimDoor |
| **Rust** | 컴파일러 최적화가 정적 분석 혼란, 메모리 안전 | BlackCat/ALPHV, Bishop Fox |
| **Go** | 정적 링킹, 크로스플랫폼, 직접 시스콜 | Sliver, ScareCrow |

### 5.5 시스콜 회피
- **직접 시스콜**: ntdll 우회 → EDR 유저랜드 후킹 무력화
- **간접 시스콜**: 정상 ntdll 스텁으로 점프
- **언후킹**: 서스펜드된 프로세스의 클린 ntdll 매핑

### 5.6 LOLBAS
주요 바이너리: `mshta.exe`, `certutil.exe`, `rundll32.exe`, `regsvr32.exe`, `wmic.exe`, `msiexec.exe`

---

## 6. Credential Access (TA0006)

### 6.1 LSASS 덤프

| 기법 | 도구 | 은밀성 |
|------|------|--------|
| sekurlsa::logonpasswords | Mimikatz | 낮음 (시그니처) |
| MiniDumpWriteDump API | 커스텀 C/C# | 중간 |
| comsvcs.dll MiniDump | rundll32 (LOLBAS) | 중간 |
| **nanodump** | 시스콜 기반 | 높음 |
| **HandleKatz** | 핸들 복제 | 높음 |

오프라인 파싱: **pypykatz** (Python Mimikatz)

### 6.2 Kerberos 티켓 공격

| 공격 | 설명 | 탐지 난이도 |
|------|------|-----------|
| **Golden Ticket** | KRBTGT 해시로 TGT 위조 → 모든 리소스 DA 접근 | 중간 |
| **Silver Ticket** | 서비스 계정 해시로 TGS 위조 | 높음 (KDC 미경유) |
| **Diamond Ticket** | 정상 TGT 수정 (위조 아닌 변조) | 매우 높음 |

### 6.3 NTLM 릴레이 (2025년에도 유효)
- **Responder**: LLMNR/NBT-NS/mDNS 포이즈닝 → 해시 캡처
- **ntlmrelayx** (Impacket): 인증 릴레이
- **PetitPotam**: MS-EFSRPC로 DC 인증 강제

### 6.4 패스워드 스프레이
- **CrackMapExec/NetExec**: AD "Swiss Army knife" — 스프레이, 검증, 횡이동, Mimikatz 원격 실행
- **DomainPasswordSpray**: PowerShell 기반

---

## 7. Lateral Movement (TA0008)

### 7.1 프로토콜별 이동

| 방법 | 도구 | 포트 | 특성 |
|------|------|------|------|
| PsExec | Impacket psexec.py | 445 (SMB) | 서비스 바이너리 복사 → 서비스 생성/시작. 노이즈 큼 |
| WMI | Impacket wmiexec.py | 135 (RPC) | 반대화형 셸. PsExec보다 적은 아티팩트 |
| WinRM | **Evil-WinRM** | 5985/5986 | 풀 인터랙티브 PowerShell, 해시 인증/파일 전송/DLL |
| SMB | Impacket smbexec.py | 445 | 서비스 기반 실행 |
| RDP | **SharpRDP** | 3389 | GUI 없이 프로그래밍 방식 RDP 커맨드 실행 |
| DCOM | Impacket dcomexec.py | 135+ | MMC20, ShellBrowserWindow 객체 |

### 7.2 Pass-the-Hash / Pass-the-Ticket
> "AD에서 NTLM 해시를 가지면 비밀번호를 가진 것과 같다"

대부분 공격 도구가 `-hashes` / `-H` 인자 지원. Kerberos 티켓은 Rubeus `ptt`, Mimikatz `kerberos::ptt`로 전달.

### 7.3 네트워크 터널링
- **Ligolo-ng**: tun 인터페이스 기반 L3 터널링 (SOCKS 불필요)
- **Chisel**: HTTP 기반 터널 (웹 포트만 열린 환경)

---

## 8. Collection & Exfiltration (TA0009/TA0010)

### 8.1 유출 채널

| 채널 | 도구 | 은밀성 |
|------|------|--------|
| DNS 터널링 | dnscat2, iodine | 높음 — 정상 DNS 혼합 |
| HTTPS C2 | 모든 주요 C2 | 중-높음 — 암호화 + 일반 포트 |
| HTTP/2-3 | **Merlin** C2 (QUIC) | 높음 — 비일반적 프로토콜 |
| 클라우드 스토리지 | rclone → S3/Azure/GDrive | 중간 — DLP 의존 |
| 스테가노그래피 | 이미지/문서 임베딩 | 높음 — 탐지 난이 |
| SMB/FTP | Impacket smbclient | 낮음 |

### 8.2 DLP 우회
- 청크 전송 (크기 임계값 미만)
- 모든 유출 데이터 암호화
- 정상 클라우드 서비스를 유출 엔드포인트로 사용
- DNS 기반 유출 (느리지만 은밀)

---

## 9. C2 인프라 (TA0011)

### 9.1 Malleable C2 & 리다이렉터
- **Malleable C2 프로필**: HTTP 트래픽을 정상 서비스(jQuery, Amazon 등)로 위장
- **RedWarden**: C2 리버스 프록시 — Blue Team/AV/샌드박스 트래픽 필터링

### 9.2 도메인 프론팅 (2025 현황)
- **사실상 종료**: Microsoft Edgio CDN 퇴역 (2025년 1월)
- **대안**: Cloudflare Workers, Azure Functions, SaaS API(Slack/Teams/Telegram) 채널

---

## 10. Cloud Red Teaming

### 10.1 Azure / Entra ID

| 도구 | 역할 |
|------|------|
| **ROADtools** | Entra ID 테넌트 열거/탐색 (비공식 MS Graph API) |
| **AADInternals** | Azure AD 내부 — 토큰 조작, 페더레이션 백도어, PRT |
| **AzureHound** | BloodHound 데이터 수집 (Azure 관계) |
| **TokenTactics** | OAuth 토큰 조작, 리프레시 토큰 남용 |
| **TeamFiltration** | O365 자격증명 스프레이 + 유출 |

**2025 핵심 공격**:
- **CVE-2025-55241** (CVSS 10.0): 크로스 테넌트 Global Admin 사칭, CA/MFA 우회, 로깅 없음
- **PRT 익스플로잇**: 탈취된 PRT + 세션 키 → 14일 접근, Windows Hello for Business 등록

### 10.2 AWS

| 도구 | 역할 |
|------|------|
| **Pacu** | AWS 익스플로잇 프레임워크 (IAM 열거, privesc, 유출, 지속성) |
| **ScoutSuite** | 멀티클라우드 감사 (AWS/Azure/GCP) |
| **CloudGoat** | 취약한 AWS 환경 (훈련용) |
| **enumerate-iam** | CloudTrail 미로깅 IAM 권한 브루트포스 |

### 10.3 멀티클라우드
- **RedCloud-OS**: 클라우드 적대자 시뮬레이션 OS (40+ 도구)
- **Stratus Red Team** (DataDog): 클라우드 ATT&CK 기법 에뮬레이션

---

## 11. Active Directory 공격 체인

### 11.1 전체 경로: 초기 발판 → 포레스트 침해

```
1. INITIAL FOOTHOLD
   피싱/익스플로잇 → 도메인 가입 워크스테이션 셸
   ↓
2. LOCAL ENUMERATION
   whoami /all, net user, BloodHound/SharpHound
   ↓
3. LOCAL PRIVILEGE ESCALATION
   Potato (SeImpersonate) → SYSTEM
   ↓
4. CREDENTIAL HARVESTING
   LSASS 덤프 (Mimikatz/nanodump) → 평문/NTLM 해시
   SAM/SECURITY/SYSTEM 하이브 → 로컬 관리자 해시
   DPAPI → 저장된 자격증명, 브라우저 비밀번호
   ↓
5. LATERAL MOVEMENT
   Pass-the-Hash (CrackMapExec) → 서브넷 전체 스프레이
   Evil-WinRM/WMI → 매칭 자격증명 타겟 인터랙티브 접근
   ↓
6. DOMAIN ENUMERATION
   BloodHound → DA 최단 경로 맵핑
   Kerberoastable, AS-REP Roastable, Unconstrained Delegation,
   ADCS 미스컨피그, GPO 남용 경로 식별
   ↓
7. DOMAIN PRIVILEGE ESCALATION (공격 경로 선택)
   a. Kerberoasting → 서비스 계정 크래킹 → DA
   b. ADCS (Certify/Certipy) → ESC1-8 → 인증서 위조 → DA
   c. Unconstrained Delegation → DC 인증 강제 → TGT → DA
   d. RBCD 남용
   e. DCSync (복제 권한) → KRBTGT 포함 전체 해시
   ↓
8. DOMAIN ADMIN
   DCSync → KRBTGT 해시 덤프
   ↓
9. PERSISTENCE
   Golden Ticket / Diamond Ticket / Silver Ticket
   Skeleton Key / AdminSDHolder
   ↓
10. FOREST COMPROMISE
    Trust ticket → 인터렐름 TGT 위조
    SID History injection → Enterprise Admin SID
    ADCS → 신뢰 경계 넘어 인증서 위조
```

### 11.2 AD 도구 체인

| 단계 | 도구 |
|------|------|
| 열거 | BloodHound + SharpHound, ADRecon, PowerView, MSLDAP |
| Kerberos | Rubeus, Impacket (GetUserSPNs, GetNPUsers, getST, secretsdump) |
| 인증서 | **Certify**, **Certipy**, ForgeCert |
| 자격증명 | Mimikatz, pypykatz, nanodump, SharpDPAPI |
| 횡이동 | CrackMapExec/NetExec, Impacket, Evil-WinRM |
| 지속성 | Mimikatz (Golden/Silver), SharPersist |
| 포레스트 | Mimikatz (trust keys), Impacket (cross-domain) |

---

## 12. 2025-2026 핵심 트렌드

1. **OSS C2 우세**: Sliver/Havoc/Mythic → 낮은 탐지 시그니처 + 무료
2. **현대 언어 로더**: Nim/Rust/Go → 정적 분석 도구가 컴파일 아티팩트 파싱 실패
3. **클라우드 퍼스트 공격**: OAuth/PRT/리프레시 토큰 탈취 → 비밀번호 기반 대체
4. **BOF 생태계 확장**: 다수 C2 프레임워크로 확산; 인메모리, 초소형
5. **도메인 프론팅 쇠퇴**: Edgio CDN 퇴역 → Cloudflare Workers, SaaS API 채널로 전환
6. **공급망 주요 벡터**: 2020년 이후 1,300% 증가; 신뢰 관계 익스플로잇이 주패턴
7. **ID 중심 공격**: DBIR 2025 기준 74% 침해가 손상된 ID 관련

---

## 참조

- Bishop Fox 2025 Red Team Tools: https://bishopfox.com/blog/2025-red-team-tools-c2-frameworks-active-directory-network-exploitation
- Picus 2025 Red Report: PowerShell in 71% LOTL attacks
- ScareCrow: https://github.com/optiv/ScareCrow
- Sliver C2: https://github.com/BishopFox/sliver
- AMSI Bypass 2025: https://undercodetesting.com/amsi-bypass-techniques-in-2025/
- AD Attack Compendium: https://undercodetesting.com/the-ultimate-active-directory-attack-compendium/
- ROADtools: https://github.com/dirkjanm/ROADtools
- Pacu: https://github.com/RhinoSecurityLabs/pacu
- Supply Chain Stats 2025: https://deepstrike.io/blog/supply-chain-attack-statistics-2025
- Verizon DBIR 2025
- RedWarden: https://github.com/mgeeky/RedWarden
- Ligolo-ng: https://github.com/nicocha30/ligolo-ng
