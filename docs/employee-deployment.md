# 직원용 읽기 전용 대시보드 배포

`employee_app.py`를 기존 관리자용 `app.py`와 **별도의 Streamlit 앱/서비스**로 배포합니다. 관리자 앱은 변경하지 않았습니다. 직원 앱은 관리자 앱과 동일한 GitHub `main/data/regulations.json` 및 `main/data/mdsap_status.json`을 60초 캐시로 읽습니다. 데이터 요청 실패 시 배포 시점의 오래된 로컬 파일로 대체하지 않고 접근 실패를 표시합니다. 배포 및 소스코드 접근 권한을 별도로 제한하세요. 읽기 전용 UI 자체는 인증·접근 통제 수단이 아닙니다.

1. 변경사항을 검토하고 승인된 절차에 따라 저장소에 반영합니다. 이 작업은 자동으로 수행하지 않습니다.
2. 별도 Streamlit 서비스의 저장소와 브랜치를 지정하고 메인 파일을 `employee_app.py`로 설정합니다. `requirements.txt` 의존성을 설치합니다. 관리자는 기존 `app.py`를 계속 사용합니다.
3. 직원 앱에는 GitHub 쓰기 토큰, 크롤러 비밀정보 또는 관리자 비밀정보를 설정하지 마세요. GitHub raw 데이터와 공식 근거 PDF에 대한 읽기 네트워크 접근만 필요합니다. 비공개 데이터가 필요하다면 별도의 안전한 읽기 전용 데이터 접근 설계를 먼저 마련해야 합니다.
4. 직원 앱에 필요한 조직 인증/접근 제한을 호스팅 플랫폼에서 설정합니다. 앱 URL 또는 쿼리 파라미터는 권한 경계가 아닙니다.
5. 배포 후 데이터 출처, 필터, 한글 요약·근거, Excel 다운로드 및 업데이트/관리 기능 부재를 확인합니다. 기본 데이터는 공개 GitHub main에서 읽으므로 관리자 앱에서 로컬 fallback을 표시 중일 때는 두 화면이 다를 수 있습니다.

별도 구현이므로 `app.py`의 화면 변경 시 직원 화면도 함께 검토해야 합니다. 로컬 실행: `streamlit run employee_app.py`. 테스트: `python -m pytest tests/test_employee_app.py tests/test_employee_safety.py -q`.
