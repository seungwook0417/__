import html
from datetime import datetime, timedelta

########################################
# 설정값: 여기만 수정해서 재사용하면 됨
########################################

TEXT_FILE = "./new.txt"  # 쉴드/좌표 목록 txt
BASE_TIME_STR = "2025-11-05 09:52:30"  # 기준 시각 (KST 기준이라고 가정)
OUTPUT_HTML = "./baad_shield_output.html"  # 만들어질 HTML 파일 경로

PAGE_TITLE = "BAAD 방어막 만료 순서"
HEADER_BADGE = "🏰"
SECTION_TITLE = "BAAD 집결지 현황"


########################################
# 유틸 함수들
########################################

WEEKDAY_KR = ['월', '화', '수', '목', '금', '토', '일']


def parse_duration(duration_text):
    """
    "1h 38m" -> (1, 38)
    "26m" -> (0, 26)
    "18m" -> (0, 18)
    "5h 23m" -> (5, 23)
    빈 문자열이나 이상한 값 -> (0,0)
    """
    duration_text = duration_text.strip()
    if not duration_text:
        return (0, 0)

    hours = 0
    minutes = 0
    parts = duration_text.split()
    for p in parts:
        p = p.strip()
        if p.endswith("h"):
            # "19h"
            try:
                hours = int(p[:-1])
            except ValueError:
                hours = 0
        elif p.endswith("m"):
            # "38m"
            try:
                minutes = int(p[:-1])
            except ValueError:
                minutes = 0
    return (hours, minutes)


def format_expire_info(base_time, hours, minutes):
    """
    기준 시각 + 남은시간 -> 만료 예정 시각, 화면용 날짜/시간(오전/오후 HH:MM),
    남은시간 표시("X시간 Y분" 또는 "Z분 0초"), total_minutes(정렬용)
    """
    expire_dt = base_time + timedelta(hours=hours, minutes=minutes)

    # yyyy-mm-ddTHH:MM:SS (초는 00으로 맞춤)
    iso_dt = expire_dt.replace(second=0)

    # "10/27 (월)"
    mon = expire_dt.month
    day = expire_dt.day
    weekday = WEEKDAY_KR[expire_dt.weekday()]
    date_disp = f"{mon:02d}/{day:02d} ({weekday})"

    # "오전/오후 HH:MM"
    hour24 = expire_dt.hour
    minute = expire_dt.minute
    ampm = "오전" if hour24 < 12 else "오후"
    hour12 = hour24 % 12
    if hour12 == 0:
        hour12 = 12
    time_disp = f"{ampm} {hour12:02d}:{minute:02d}"

    # 남은시간 표기
    if hours == 0:
        countdown = f"{minutes}분 0초"
    else:
        countdown = f"{hours}시간 {minutes}분"

    total_minutes = hours * 60 + minutes

    return {
        "iso_dt": iso_dt,
        "date_disp": date_disp,
        "time_disp": time_disp,
        "countdown": countdown,
        "total_minutes": total_minutes,
    }


def build_row_html(row):
    """
    row dict -> <tr>...</tr> HTML
    row keys:
      name, coord, is_expired(bool)
      if expired:
          countdown='지남', date_disp/time_disp='-', iso_dt=None
      else:
          date_disp, time_disp, countdown, iso_dt
    """
    esc_name = html.escape(row["name"])
    coord_txt = f"{row['x']}, {row['y']}"

    if row["is_expired"]:
        date_html = '<div class="text-xs text-gray-400">만료</div>'
        time_html = '<div class="text-gray-400">-</div>'
        cd_class = "text-gray-400"
        cd_text = html.escape(row["countdown"])
        data_dt_attr = ""
        time_block_class = "text-gray-400"
        data_status = "expired"
        data_minutes = "-1"
    else:
        date_html = f'<div class="text-xs text-gray-500">{html.escape(row["date_disp"])}</div>'
        time_html = f'<div>{html.escape(row["time_disp"])}</div>'
        cd_class = "text-red-600 font-bold"
        cd_text = html.escape(row["countdown"])
        data_dt_attr = row["iso_dt"].strftime("%Y-%m-%dT%H:%M:%S")
        time_block_class = "text-gray-600"
        data_status = "active"
        data_minutes = str(row["total_minutes"])

    return f'''<tr class="hover:bg-gray-50 commander-row" data-datetime="{data_dt_attr}" data-status="{data_status}" data-minutes="{data_minutes}" data-name="{esc_name.lower()}" data-x="{row['x']}" data-y="{row['y']}">
  <td class="px-6 py-4 text-sm text-gray-900 font-medium">{esc_name}</td>
  <td class="px-6 py-4 text-sm text-blue-600 cursor-pointer hover:text-blue-800 hover:underline" onclick="copyCoordinates('{coord_txt}')">({coord_txt})</td>
  <td class="px-6 py-4 text-sm">
    <div class="flex items-center justify-between">
      <div class="time-display {time_block_class}">
        {date_html}
        {time_html}
      </div>
      <span class="countdown-display text-xs font-mono ml-4 {cd_class}">{cd_text}</span>
    </div>
  </td>
</tr>'''


########################################
# 파서: txt를 읽어서 row 리스트로 변환
########################################

def parse_txt_lines(lines, base_time):
    """
    lines: txt 전체 라인 리스트
    base_time: datetime 기준 시각
    return: rows(list of dict)
        {
          "name": str,
          "x": str,
          "y": str,
          "is_expired": bool,
          "countdown": str,           # "지남" or "X시간 Y분" 등
          "date_disp": ...,
          "time_disp": ...,
          "iso_dt": datetime or None,
          "total_minutes": int        # 정렬용 (만료는 -1)
        }
    """
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # 좌표가 들어간 main 라인인지 판별
        # 예: "BAA 자이언트\tBAAD\t30\t(122, 513)\t"
        # 또는 "Just Uh Casual\tBAAD\t30\t(942, 65)\t-"
        if "(" in line and ")" in line and "\t" in line:
            parts = line.split("\t")
            # 기대형식:
            # parts[0] = 이름
            # parts[1] = "BAAD"
            # parts[2] = HQ 레벨
            # parts[3] = "(x, y)"
            # parts[4] = "-" or "" (있을수도 없을수도)
            if len(parts) < 4:
                i += 1
                continue

            name = parts[0].strip()
            coord_part = parts[3].strip()

            # 좌표 파싱 "(x, y)" -> x, y
            if coord_part.startswith("(") and coord_part.endswith(")"):
                coord_part_inner = coord_part[1:-1]
            else:
                coord_part_inner = coord_part
            xy_split = coord_part_inner.split(",")
            if len(xy_split) == 2:
                x = xy_split[0].strip()
                y = xy_split[1].strip()
            else:
                x = ""
                y = ""

            # 실드 만료 여부
            last_col = ""
            if len(parts) >= 5:
                last_col = parts[4].strip()

            if last_col == "-":
                # 이미 만료된 상태
                rows.append({
                    "name": name,
                    "x": x,
                    "y": y,
                    "is_expired": True,
                    "countdown": "지남",
                    "date_disp": "-",
                    "time_disp": "-",
                    "iso_dt": None,
                    "total_minutes": -1,
                })
                i += 1
                continue
            else:
                # 방어막 남아있음:
                # 다음 줄은 "🛡️", 그 다음 줄은 남은시간 예: "1h 38m"
                remaining_text = ""
                if i + 2 < len(lines):
                    # i+1 은 🛡️, i+2 는 "1h 38m"
                    remaining_text = lines[i + 2].strip()
                hours, minutes = parse_duration(remaining_text)
                info = format_expire_info(base_time, hours, minutes)

                rows.append({
                    "name": name,
                    "x": x,
                    "y": y,
                    "is_expired": False,
                    "countdown": info["countdown"],
                    "date_disp": info["date_disp"],
                    "time_disp": info["time_disp"],
                    "iso_dt": info["iso_dt"],
                    "total_minutes": info["total_minutes"],
                })

                i += 3
                continue

        # 기본적으로 조건 안 맞으면 다음 라인
        i += 1

    return rows


########################################
# HTML 생성
########################################

def build_html(rows, base_time):
    """
    rows: parse_txt_lines 결과
    base_time: datetime
    -> 최종 HTML 문자열
    """
    # 정렬: 만료(-1)먼저, 그 다음 남은시간(total_minutes) 오름차순
    sorted_rows = sorted(rows, key=lambda r: r["total_minutes"])

    table_rows_html = "\n".join(build_row_html(r) for r in sorted_rows)

    base_time_disp = base_time.strftime("%Y-%m-%d %H:%M:%S")

    # 통계 계산
    total_count = len(rows)
    expired_count = sum(1 for r in rows if r["is_expired"])
    active_count = total_count - expired_count
    critical_count = sum(1 for r in rows if not r["is_expired"] and r["total_minutes"] <= 30)

    # 지도용 데이터 생성 (JSON)
    map_data = []
    for r in sorted_rows:
        map_data.append({
            "name": r["name"],
            "x": int(r["x"]) if r["x"].isdigit() else 0,
            "y": int(r["y"]) if r["y"].isdigit() else 0,
            "is_expired": r["is_expired"],
            "total_minutes": r["total_minutes"],
            "countdown": r["countdown"],
            "date_disp": r.get("date_disp", "-"),
            "time_disp": r.get("time_disp", "-")
        })

    import json
    map_data_json = json.dumps(map_data)

    html_out = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(PAGE_TITLE)}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body {{ box-sizing: border-box; }}
    .tab-active {{
      background-color: rgb(59 130 246);
      color: white;
    }}
    .filter-active {{
      background-color: rgb(59 130 246);
      color: white;
    }}
    #mapView {{
      position: relative;
      background: linear-gradient(to bottom right, #f0f9ff, #e0e7ff);
      border-radius: 0.5rem;
    }}
    #mapSvg {{
      cursor: grab;
    }}
    #mapSvg.dragging {{
      cursor: grabbing;
    }}
    .map-marker {{
      cursor: pointer;
      transition: opacity 0.2s;
    }}
    .map-marker:hover {{
      opacity: 0.8;
    }}
    .map-marker.selected {{
      filter: drop-shadow(0 0 4px rgba(59, 130, 246, 0.8));
    }}
    .map-info-card {{
      position: absolute;
      top: 20px;
      right: 20px;
      background: white;
      padding: 16px;
      border-radius: 12px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.1);
      z-index: 1000;
      min-width: 280px;
      max-width: 90%;
      display: none;
      border: 2px solid rgb(59 130 246);
    }}
    .map-info-card.show {{
      display: block;
      animation: slideIn 0.2s ease-out;
    }}
    @keyframes slideIn {{
      from {{
        opacity: 0;
        transform: translateY(-10px);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    .coord-copy-btn {{
      cursor: pointer;
      transition: all 0.2s;
    }}
    .coord-copy-btn:hover {{
      background-color: rgb(59 130 246);
      color: white;
    }}
    .coord-copy-btn:active {{
      transform: scale(0.95);
    }}
    .zoom-controls {{
      position: absolute;
      bottom: 20px;
      right: 20px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      z-index: 100;
    }}
    .zoom-btn {{
      width: 40px;
      height: 40px;
      background: white;
      border: 2px solid rgb(59 130 246);
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 20px;
      font-weight: bold;
      color: rgb(59 130 246);
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
      transition: all 0.2s;
      user-select: none;
    }}
    .zoom-btn:hover:not([style*="cursor: default"]) {{
      background: rgb(59 130 246);
      color: white;
    }}
    .zoom-btn:active:not([style*="cursor: default"]) {{
      transform: scale(0.95);
    }}
    #zoomLevel {{
      min-width: 48px;
      font-family: monospace;
      letter-spacing: 0.5px;
    }}
    @media (max-width: 768px) {{
      .stats-grid {{ grid-template-columns: repeat(2, 1fr) !important; }}

      /* 모바일 컨테이너 패딩 줄이기 */
      .container {{
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
      }}

      /* 모바일 지도 컨테이너 - 화면에 맞춤 */
      .map-container {{
        aspect-ratio: auto !important;
        width: 100% !important;
        height: 400px !important;
        max-height: none !important;
        margin-left: 0;
        margin-right: 0;
      }}

      /* 모바일 지도 뷰 섹션 */
      #mapView {{
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
      }}

      /* 모바일 정보 카드 - 바텀시트 스타일 */
      .map-info-card {{
        top: auto;
        bottom: 0;
        left: 0;
        right: 0;
        transform: none;
        min-width: auto;
        width: 100%;
        max-width: none;
        border-radius: 16px 16px 0 0;
        max-height: 50vh;
        overflow-y: auto;
        box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.15);
      }}
      .map-info-card.show {{
        animation: slideUpMobile 0.3s ease-out;
      }}

      /* 모바일 줌 컨트롤 - 더 작고 투명하게 */
      .zoom-controls {{
        bottom: 10px;
        right: 10px;
        gap: 6px;
      }}
      .zoom-btn {{
        width: 36px;
        height: 36px;
        font-size: 18px;
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(8px);
      }}
      #zoomLevel {{
        min-width: 42px;
        font-size: 11px;
      }}

    }}
    @keyframes slideUpMobile {{
      from {{
        opacity: 0;
        transform: translateY(100%);
      }}
      to {{
        opacity: 1;
        transform: translateY(0);
      }}
    }}
    @keyframes slideInMobile {{
      from {{
        opacity: 0;
        transform: translateX(-50%) translateY(-20px);
      }}
      to {{
        opacity: 1;
        transform: translateX(-50%) translateY(0);
      }}
    }}
  </style>
</head>
<body class="bg-gradient-to-br from-blue-50 to-indigo-100 min-h-screen font-sans">
  <div class="container mx-auto px-4 py-8 max-w-7xl">
    <!-- Header -->
    <header class="text-center mb-8">
      <h1 class="text-4xl font-bold text-gray-800 mb-2">{html.escape(PAGE_TITLE)}</h1>
      <p class="text-gray-600">기준 시각: <span id="baseTime">{html.escape(base_time_disp)}</span> (KST)</p>
      <p class="text-gray-500 text-sm">실시간 카운트다운 업데이트 중</p>
    </header>

    <!-- Statistics Dashboard -->
    <div class="grid grid-cols-4 gap-4 mb-6 stats-grid">
      <div class="bg-white rounded-lg shadow-md p-4 text-center">
        <div class="text-3xl font-bold text-blue-600">{total_count}</div>
        <div class="text-sm text-gray-600 mt-1">전체</div>
      </div>
      <div class="bg-white rounded-lg shadow-md p-4 text-center">
        <div class="text-3xl font-bold text-green-600" id="statActive">{active_count}</div>
        <div class="text-sm text-gray-600 mt-1">보호막 활성</div>
      </div>
      <div class="bg-white rounded-lg shadow-md p-4 text-center">
        <div class="text-3xl font-bold text-gray-400" id="statExpired">{expired_count}</div>
        <div class="text-sm text-gray-600 mt-1">만료됨</div>
      </div>
      <div class="bg-white rounded-lg shadow-md p-4 text-center">
        <div class="text-3xl font-bold text-red-600" id="statCritical">{critical_count}</div>
        <div class="text-sm text-gray-600 mt-1">30분 이하</div>
      </div>
    </div>

    <!-- Filter Controls -->
    <div class="bg-white rounded-lg shadow-md p-4 mb-6">
      <div class="flex flex-wrap gap-3 items-center">
        <div class="flex gap-2 flex-wrap">
          <button onclick="filterRows('all')" class="filter-btn filter-active px-4 py-2 rounded-md bg-gray-200 hover:bg-blue-500 hover:text-white transition" data-filter="all">
            전체
          </button>
          <button onclick="filterRows('active')" class="filter-btn px-4 py-2 rounded-md bg-gray-200 hover:bg-blue-500 hover:text-white transition" data-filter="active">
            보호막 있음
          </button>
          <button onclick="filterRows('expired')" class="filter-btn px-4 py-2 rounded-md bg-gray-200 hover:bg-blue-500 hover:text-white transition" data-filter="expired">
            보호막 없음
          </button>
          <button onclick="filterRows('critical')" class="filter-btn px-4 py-2 rounded-md bg-gray-200 hover:bg-blue-500 hover:text-white transition" data-filter="critical">
            30분 이하
          </button>
        </div>
        <div class="flex-1 min-w-[200px]">
          <input type="text" id="searchInput" placeholder="커맨더 이름 검색..."
                 class="w-full px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                 oninput="searchCommanders()">
        </div>
      </div>
    </div>

    <!-- View Toggle Tabs -->
    <div class="bg-white rounded-t-lg shadow-md">
      <div class="flex border-b border-gray-200">
        <button onclick="switchView('list')" class="tab-btn tab-active px-6 py-3 font-semibold focus:outline-none" data-view="list">
          📋 리스트형
        </button>
        <button onclick="switchView('map')" class="tab-btn px-6 py-3 font-semibold focus:outline-none" data-view="map">
          🗺️ 지도형
        </button>
      </div>
    </div>

    <!-- List View -->
    <div id="listView" class="bg-white rounded-b-lg shadow-md overflow-hidden">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-blue-50 text-left sticky top-0">
            <tr>
              <th class="px-6 py-3 text-xs font-semibold text-gray-700 uppercase tracking-wider">Commander</th>
              <th class="px-6 py-3 text-xs font-semibold text-gray-700 uppercase tracking-wider">좌표</th>
              <th class="px-6 py-3 text-xs font-semibold text-gray-700 uppercase tracking-wider">방어막 종료 / 남은시간</th>
            </tr>
          </thead>
          <tbody id="commanderTableBody">
{table_rows_html}
          </tbody>
        </table>
      </div>
      <div id="noResults" class="hidden text-center py-12 text-gray-500">
        검색 결과가 없습니다.
      </div>
    </div>

    <!-- Map View -->
    <div id="mapView" class="bg-white rounded-b-lg shadow-md p-6 hidden">
      <div class="mb-4 flex justify-between items-center flex-wrap gap-3">
        <h3 class="text-lg font-semibold text-gray-800">라스트워 시즌1 맵 (1000x1000)</h3>
        <div class="text-sm text-gray-600">
          <span class="inline-block w-3 h-3 rounded-full bg-green-500 mr-1"></span> 활성
          <span class="inline-block w-3 h-3 rounded-full bg-red-500 ml-3 mr-1"></span> 긴급
          <span class="inline-block w-3 h-3 rounded-full bg-gray-400 ml-3 mr-1"></span> 만료
        </div>
      </div>
      <div class="relative border-2 border-gray-300 rounded overflow-hidden map-container" style="aspect-ratio: 1/1; max-height: 700px;">
        <svg id="mapSvg" class="w-full h-full" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid meet" style="display: block;">
          <!-- Grid lines -->
          <defs>
            <pattern id="grid" width="100" height="100" patternUnits="userSpaceOnUse">
              <path d="M 100 0 L 0 0 0 100" fill="none" stroke="rgba(0,0,0,0.05)" stroke-width="1"/>
            </pattern>
          </defs>
          <rect width="1000" height="1000" fill="url(#grid)" />

          <!-- Markers will be inserted here -->
          <g id="markers"></g>
        </svg>

        <!-- Zoom Controls -->
        <div class="zoom-controls">
          <div id="zoomLevel" class="zoom-btn" style="font-size: 12px; font-weight: normal; cursor: default; background: rgba(255,255,255,0.95);">×1.0</div>
          <button class="zoom-btn" onclick="zoomIn()" title="확대">+</button>
          <button class="zoom-btn" onclick="zoomOut()" title="축소">−</button>
          <button class="zoom-btn" onclick="resetZoom()" title="초기화" style="font-size: 16px;">⟲</button>
        </div>

        <!-- Info Card -->
        <div id="mapInfoCard" class="map-info-card">
          <!-- 모바일 바텀시트 핸들 -->
          <div class="md:hidden w-12 h-1 bg-gray-300 rounded-full mx-auto mb-3"></div>

          <div class="flex justify-between items-start mb-3">
            <h4 class="text-lg font-bold text-gray-800" id="infoName"></h4>
            <button onclick="closeInfoCard()" class="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>
          <div class="space-y-2">
            <div class="text-sm text-gray-600">
              <span class="font-semibold">상태:</span>
              <span id="infoStatus" class="ml-2"></span>
            </div>
            <div id="infoExpireTime" class="text-sm text-gray-600" style="display: none;">
              <span class="font-semibold">종료시각:</span>
              <span id="infoExpireTimeValue" class="ml-2"></span>
            </div>
            <div class="text-sm text-gray-600">
              <span class="font-semibold">남은시간:</span>
              <span id="infoCountdown" class="ml-2"></span>
            </div>
            <div class="pt-2 border-t border-gray-200">
              <div class="text-xs text-gray-500 mb-1">좌표 (클릭하여 복사)</div>
              <button id="coordCopyBtn" class="coord-copy-btn w-full px-4 py-2 bg-gray-100 text-gray-800 rounded-md font-mono text-sm font-semibold hover:bg-blue-500 hover:text-white transition">
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>

  <script>
    const BASE_TIME = new Date('{base_time.strftime("%Y-%m-%dT%H:%M:%S")}');
    const MAP_DATA = {map_data_json};
    let currentFilter = 'all';
    let currentView = 'list';

    // 줌 관련 변수
    let currentZoom = 1;
    let currentPanX = 0;
    let currentPanY = 0;
    let selectedMarker = null;

    // 드래그 관련 변수
    let isDragging = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragStartPanX = 0;
    let dragStartPanY = 0;

    // 좌표 복사
    function copyCoordinates(coords) {{
      if (navigator.clipboard) {{
        navigator.clipboard.writeText(coords).then(function() {{
          alert('좌표 ' + coords + ' 복사됨');
        }}, function() {{
          alert('복사 실패');
        }});
      }} else {{
        alert('클립보드 권한 없음');
      }}
    }}

    // 뷰 전환
    function switchView(view) {{
      currentView = view;
      const listView = document.getElementById('listView');
      const mapView = document.getElementById('mapView');
      const tabs = document.querySelectorAll('.tab-btn');

      tabs.forEach(tab => {{
        if (tab.dataset.view === view) {{
          tab.classList.add('tab-active');
        }} else {{
          tab.classList.remove('tab-active');
        }}
      }});

      if (view === 'list') {{
        listView.classList.remove('hidden');
        mapView.classList.add('hidden');
      }} else {{
        listView.classList.add('hidden');
        mapView.classList.remove('hidden');
        // 지도형으로 전환 시에만 렌더링
        setTimeout(() => renderMap(), 50); // 약간의 딜레이로 중복 방지
      }}
    }}

    // 필터 적용
    function filterRows(filter) {{
      currentFilter = filter;
      const rows = document.querySelectorAll('.commander-row');
      const filterBtns = document.querySelectorAll('.filter-btn');
      let visibleCount = 0;

      filterBtns.forEach(btn => {{
        if (btn.dataset.filter === filter) {{
          btn.classList.add('filter-active');
        }} else {{
          btn.classList.remove('filter-active');
        }}
      }});

      rows.forEach(row => {{
        const status = row.dataset.status;
        const minutes = parseInt(row.dataset.minutes);
        let show = false;

        if (filter === 'all') show = true;
        else if (filter === 'active') show = status === 'active';
        else if (filter === 'expired') show = status === 'expired';
        else if (filter === 'critical') show = status === 'active' && minutes <= 30;

        if (show) {{
          row.style.display = '';
          visibleCount++;
        }} else {{
          row.style.display = 'none';
        }}
      }});

      document.getElementById('noResults').classList.toggle('hidden', visibleCount > 0);
      updateStats();
      if (currentView === 'map') renderMap();
    }}

    // 검색
    function searchCommanders() {{
      const searchTerm = document.getElementById('searchInput').value.toLowerCase();
      const rows = document.querySelectorAll('.commander-row');
      let visibleCount = 0;

      rows.forEach(row => {{
        const name = row.dataset.name;
        const matchesSearch = name.includes(searchTerm);
        const status = row.dataset.status;
        const minutes = parseInt(row.dataset.minutes);
        let matchesFilter = false;

        if (currentFilter === 'all') matchesFilter = true;
        else if (currentFilter === 'active') matchesFilter = status === 'active';
        else if (currentFilter === 'expired') matchesFilter = status === 'expired';
        else if (currentFilter === 'critical') matchesFilter = status === 'active' && minutes <= 30;

        if (matchesSearch && matchesFilter) {{
          row.style.display = '';
          visibleCount++;
        }} else {{
          row.style.display = 'none';
        }}
      }});

      document.getElementById('noResults').classList.toggle('hidden', visibleCount > 0);
      if (currentView === 'map') renderMap();
    }}

    // 통계 업데이트
    function updateStats() {{
      const rows = document.querySelectorAll('.commander-row');
      let active = 0, expired = 0, critical = 0;

      rows.forEach(row => {{
        const status = row.dataset.status;
        const minutes = parseInt(row.dataset.minutes);

        if (status === 'active') {{
          active++;
          if (minutes <= 30) critical++;
        }} else {{
          expired++;
        }}
      }});

      document.getElementById('statActive').textContent = active;
      document.getElementById('statExpired').textContent = expired;
      document.getElementById('statCritical').textContent = critical;
    }}

    // 줌 레벨 표시 업데이트
    function updateZoomDisplay() {{
      const zoomLevelEl = document.getElementById('zoomLevel');
      if (zoomLevelEl) {{
        zoomLevelEl.textContent = `×${{currentZoom.toFixed(1)}}`;
        // 확대 상태 시각적 표시
        if (currentZoom > 1) {{
          zoomLevelEl.style.background = 'rgb(59 130 246)';
          zoomLevelEl.style.color = 'white';
          zoomLevelEl.style.fontWeight = 'bold';
        }} else {{
          zoomLevelEl.style.background = 'rgba(255,255,255,0.95)';
          zoomLevelEl.style.color = 'rgb(59 130 246)';
          zoomLevelEl.style.fontWeight = 'normal';
        }}
      }}
    }}

    // 줌 기능
    function updateViewBox() {{
      const svg = document.getElementById('mapSvg');
      const size = 1000 / currentZoom;
      const x = currentPanX - size / 2;
      const y = currentPanY - size / 2;
      svg.setAttribute('viewBox', `${{x}} ${{y}} ${{size}} ${{size}}`);
      updateZoomDisplay();
    }}

    function zoomIn() {{
      if (currentZoom < 5) {{
        currentZoom *= 1.5;
        if (currentZoom > 5) currentZoom = 5;
        updateViewBox();
      }}
    }}

    function zoomOut() {{
      if (currentZoom > 1) {{
        currentZoom /= 1.5;
        if (currentZoom < 1) currentZoom = 1;
        updateViewBox();
      }}
    }}

    function resetZoom() {{
      currentZoom = 1;
      currentPanX = 500;
      currentPanY = 500;
      updateViewBox();
    }}

    // 정보 카드 표시
    function showInfoCard(commander) {{
      const infoCard = document.getElementById('mapInfoCard');
      const infoName = document.getElementById('infoName');
      const infoStatus = document.getElementById('infoStatus');
      const infoExpireTime = document.getElementById('infoExpireTime');
      const infoExpireTimeValue = document.getElementById('infoExpireTimeValue');
      const infoCountdown = document.getElementById('infoCountdown');
      const coordCopyBtn = document.getElementById('coordCopyBtn');

      infoName.textContent = commander.name;

      // 상태 표시
      if (commander.is_expired) {{
        infoStatus.innerHTML = '<span class="text-gray-500">🔴 만료됨</span>';
        infoExpireTime.style.display = 'none';
      }} else if (commander.total_minutes <= 30) {{
        infoStatus.innerHTML = '<span class="text-red-600">⚠️ 긴급 (30분 이하)</span>';
        infoExpireTime.style.display = 'block';
        infoExpireTimeValue.textContent = `${{commander.date_disp}} ${{commander.time_disp}}`;
      }} else {{
        infoStatus.innerHTML = '<span class="text-green-600">✅ 활성</span>';
        infoExpireTime.style.display = 'block';
        infoExpireTimeValue.textContent = `${{commander.date_disp}} ${{commander.time_disp}}`;
      }}

      infoCountdown.textContent = commander.countdown;

      const coords = `${{commander.x}}, ${{commander.y}}`;
      coordCopyBtn.textContent = `(${{coords}})`;
      coordCopyBtn.onclick = () => {{
        copyCoordinates(coords);
        coordCopyBtn.textContent = '✓ 복사됨!';
        setTimeout(() => {{
          coordCopyBtn.textContent = `(${{coords}})`;
        }}, 1500);
      }};

      infoCard.classList.add('show');
    }}

    // 정보 카드 닫기
    function closeInfoCard() {{
      document.getElementById('mapInfoCard').classList.remove('show');
    }}

    // 지도 렌더링 - DOM 데이터 기반 (실시간 반영)
    function renderMap() {{
      const markersGroup = document.getElementById('markers');
      if (!markersGroup) return; // 마커 그룹이 없으면 중단

      const searchTerm = document.getElementById('searchInput').value.toLowerCase();

      // 기존 마커 완전히 제거 (중복 방지)
      while (markersGroup.firstChild) {{
        markersGroup.removeChild(markersGroup.firstChild);
      }}

      // 지도 재렌더링 시 선택 초기화
      selectedMarker = null;

      // DOM의 row 데이터를 사용 (실시간으로 업데이트되는 데이터)
      const rows = document.querySelectorAll('.commander-row');

      rows.forEach(row => {{
        // DOM에서 실시간 데이터 읽기
        const name = row.querySelector('td:first-child').textContent.trim();
        const x = parseInt(row.dataset.x);
        const y = parseInt(row.dataset.y);
        const status = row.dataset.status; // 'active' or 'expired'
        const minutes = parseInt(row.dataset.minutes);
        const datetime = row.dataset.datetime;

        // 좌표가 유효하지 않으면 스킵
        if (isNaN(x) || isNaN(y)) return;

        // 필터 체크
        const matchesSearch = name.toLowerCase().includes(searchTerm);
        let matchesFilter = false;

        if (currentFilter === 'all') matchesFilter = true;
        else if (currentFilter === 'active') matchesFilter = status === 'active';
        else if (currentFilter === 'expired') matchesFilter = status === 'expired';
        else if (currentFilter === 'critical') matchesFilter = status === 'active' && minutes <= 30;

        if (!matchesSearch || !matchesFilter) return;

        // 색상 결정 - 실시간 상태 기반
        let color;
        if (status === 'expired') {{
          color = '#9CA3AF'; // gray
        }} else if (minutes <= 30) {{
          color = '#EF4444'; // red
        }} else {{
          color = '#10B981'; // green
        }}

        // 카운트다운 텍스트 가져오기
        const countdownEl = row.querySelector('.countdown-display');
        const countdown = countdownEl ? countdownEl.textContent : '정보 없음';

        // 날짜/시간 정보 가져오기
        const timeDisplayEl = row.querySelector('.time-display');
        let dateDisp = '-';
        let timeDisp = '-';
        if (timeDisplayEl) {{
          const dateEl = timeDisplayEl.querySelector('.text-xs');
          const timeEl = timeDisplayEl.querySelector('div:not(.text-xs)');
          if (dateEl) dateDisp = dateEl.textContent.trim();
          if (timeEl) timeDisp = timeEl.textContent.trim();
        }}

        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', 1000 - y); // Y축 반전

        // 모바일에서 마커 크기 증가
        const isMobile = window.innerWidth <= 768;
        circle.setAttribute('r', isMobile ? '10' : '8');
        circle.setAttribute('stroke-width', isMobile ? '3' : '2');

        circle.setAttribute('fill', color);
        circle.setAttribute('stroke', 'white');
        circle.classList.add('map-marker');
        circle.dataset.name = name;

        circle.addEventListener('click', (e) => {{
          e.stopPropagation();

          // 이전 선택된 마커 하이라이트 제거
          if (selectedMarker) {{
            selectedMarker.classList.remove('selected');
          }}

          // 현재 마커 하이라이트
          circle.classList.add('selected');
          selectedMarker = circle;

          // 실시간 데이터로 정보 카드 표시
          const commanderData = {{
            name: name,
            x: x,
            y: y,
            is_expired: status === 'expired',
            total_minutes: minutes,
            countdown: countdown,
            date_disp: dateDisp,
            time_disp: timeDisp
          }};

          showInfoCard(commanderData);

          // 클릭한 마커로 부드럽게 이동 (확대 없이)
          // 확대된 상태일 때만 센터링
          if (currentZoom > 1) {{
            currentPanX = x;
            currentPanY = 1000 - y;
            updateViewBox();
          }}
        }});

        markersGroup.appendChild(circle);
      }});
    }}

    // 맵 영역 클릭 시 정보 카드 닫기 및 줌 초기화
    document.addEventListener('DOMContentLoaded', () => {{
      const mapSvg = document.getElementById('mapSvg');
      const mapContainer = mapSvg.parentElement;

      if (mapSvg) {{
        let clickTimeout = null;
        let isClick = true;

        mapSvg.addEventListener('mousedown', (e) => {{
          // 마커 클릭이 아닐 때만 드래그 시작
          if (e.target === mapSvg || e.target.tagName === 'rect' || e.target.tagName === 'g') {{
            isDragging = true;
            isClick = true;
            dragStartX = e.clientX;
            dragStartY = e.clientY;
            dragStartPanX = currentPanX;
            dragStartPanY = currentPanY;
            mapSvg.classList.add('dragging');
          }}
        }});

        mapSvg.addEventListener('mousemove', (e) => {{
          if (isDragging) {{
            isClick = false;
            const rect = mapSvg.getBoundingClientRect();
            const scaleX = 1000 / currentZoom / rect.width;
            const scaleY = 1000 / currentZoom / rect.height;
            const dx = (e.clientX - dragStartX) * scaleX;
            const dy = (e.clientY - dragStartY) * scaleY;

            currentPanX = dragStartPanX - dx;
            currentPanY = dragStartPanY - dy;

            // 맵 경계 제한
            const halfSize = 500 / currentZoom;
            currentPanX = Math.max(halfSize, Math.min(1000 - halfSize, currentPanX));
            currentPanY = Math.max(halfSize, Math.min(1000 - halfSize, currentPanY));

            updateViewBox();
          }}
        }});

        mapSvg.addEventListener('mouseup', (e) => {{
          if (isDragging) {{
            isDragging = false;
            mapSvg.classList.remove('dragging');

            // 드래그가 아니라 클릭이었다면
            if (isClick) {{
              closeInfoCard();
              if (selectedMarker) {{
                selectedMarker.classList.remove('selected');
                selectedMarker = null;
              }}
            }}
          }}
        }});

        mapSvg.addEventListener('mouseleave', () => {{
          if (isDragging) {{
            isDragging = false;
            mapSvg.classList.remove('dragging');
          }}
        }});

        // 터치 드래그 및 핀치 줌
        let touchStartForDrag = null;
        let touchStartDistance = 0;
        let touchStartZoom = 1;

        mapContainer.addEventListener('touchstart', (e) => {{
          if (e.touches.length === 1) {{
            // 단일 터치 - 드래그
            const touch = e.touches[0];
            if (e.target === mapSvg || e.target.tagName === 'rect' || e.target.tagName === 'g') {{
              isDragging = true;
              isClick = true;
              touchStartForDrag = touch;
              dragStartX = touch.clientX;
              dragStartY = touch.clientY;
              dragStartPanX = currentPanX;
              dragStartPanY = currentPanY;
            }}
          }} else if (e.touches.length === 2) {{
            // 핀치 줌
            isDragging = false;
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            touchStartDistance = Math.sqrt(dx * dx + dy * dy);
            touchStartZoom = currentZoom;
          }}
        }});

        mapContainer.addEventListener('touchmove', (e) => {{
          if (e.touches.length === 1 && isDragging) {{
            // 단일 터치 드래그
            e.preventDefault();
            isClick = false;
            const touch = e.touches[0];
            const rect = mapSvg.getBoundingClientRect();
            const scaleX = 1000 / currentZoom / rect.width;
            const scaleY = 1000 / currentZoom / rect.height;
            const dx = (touch.clientX - dragStartX) * scaleX;
            const dy = (touch.clientY - dragStartY) * scaleY;

            currentPanX = dragStartPanX - dx;
            currentPanY = dragStartPanY - dy;

            // 맵 경계 제한
            const halfSize = 500 / currentZoom;
            currentPanX = Math.max(halfSize, Math.min(1000 - halfSize, currentPanX));
            currentPanY = Math.max(halfSize, Math.min(1000 - halfSize, currentPanY));

            updateViewBox();
          }} else if (e.touches.length === 2) {{
            // 핀치 줌
            e.preventDefault();
            isDragging = false;
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            const distance = Math.sqrt(dx * dx + dy * dy);
            const scale = distance / touchStartDistance;
            const newZoom = touchStartZoom * scale;

            if (newZoom >= 1 && newZoom <= 5) {{
              currentZoom = newZoom;
              updateViewBox();
            }}
          }}
        }});

        mapContainer.addEventListener('touchend', () => {{
          if (isDragging && isClick) {{
            // 클릭으로 간주
            closeInfoCard();
            if (selectedMarker) {{
              selectedMarker.classList.remove('selected');
              selectedMarker = null;
            }}
          }}
          isDragging = false;
        }});

        // 마우스 휠로 줌
        mapContainer.addEventListener('wheel', (e) => {{
          e.preventDefault();
          if (e.deltaY < 0) {{
            zoomIn();
          }} else {{
            zoomOut();
          }}
        }});
      }}

      // 줌 초기화
      currentPanX = 500;
      currentPanY = 500;
      updateZoomDisplay();
    }});

    // 실시간 카운트다운 업데이트
    function updateCountdowns() {{
      const now = new Date();
      const rows = document.querySelectorAll('.commander-row');
      let needsStatsUpdate = false;

      rows.forEach(row => {{
        const datetime = row.dataset.datetime;
        if (!datetime) return;

        const expireTime = new Date(datetime);
        const diff = expireTime - now;

        if (diff <= 0) {{
          const countdownEl = row.querySelector('.countdown-display');
          if (countdownEl && !countdownEl.classList.contains('text-gray-400')) {{
            countdownEl.textContent = '만료됨';
            countdownEl.classList.remove('text-red-600', 'font-bold');
            countdownEl.classList.add('text-gray-400');
            row.dataset.status = 'expired';
            row.dataset.minutes = '-1';
            needsStatsUpdate = true;
          }}
        }} else {{
          const totalMinutes = Math.floor(diff / 1000 / 60);
          const hours = Math.floor(totalMinutes / 60);
          const minutes = totalMinutes % 60;
          const seconds = Math.floor((diff / 1000) % 60);

          // 이전 값과 비교
          const oldMinutes = parseInt(row.dataset.minutes);
          if (oldMinutes !== totalMinutes) {{
            // 30분 경계를 넘었는지 확인
            if ((oldMinutes > 30 && totalMinutes <= 30) || (oldMinutes <= 30 && totalMinutes > 30)) {{
              needsStatsUpdate = true;
            }}
            row.dataset.minutes = totalMinutes;
          }}

          const countdownEl = row.querySelector('.countdown-display');
          if (countdownEl) {{
            if (hours > 0) {{
              countdownEl.textContent = `${{hours}}시간 ${{minutes}}분`;
            }} else {{
              countdownEl.textContent = `${{minutes}}분 ${{seconds}}초`;
            }}
          }}
        }}
      }});

      // 통계 업데이트가 필요한 경우에만 실행
      if (needsStatsUpdate) {{
        updateStats();
        // 지도형이 활성화되어 있으면 지도도 업데이트
        if (currentView === 'map') {{
          renderMap();
        }}
      }}
    }}

    // 1초마다 카운트다운 업데이트
    setInterval(updateCountdowns, 1000);

    // 초기 렌더링
    updateCountdowns();
    updateStats();
  </script>
</body>
</html>
"""
    return html_out


########################################
# 메인 실행부
########################################

def main():
    # 기준 시각 파싱
    base_time = datetime.strptime(BASE_TIME_STR, "%Y-%m-%d %H:%M:%S")

    # txt 읽기
    with open(TEXT_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 파싱
    rows = parse_txt_lines(lines, base_time)

    # HTML 생성
    html_result = build_html(rows, base_time)

    # 저장
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_result)

    print(f"완료: {OUTPUT_HTML} 에 HTML 생성됨")


if __name__ == "__main__":
    main()
