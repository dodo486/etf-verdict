/* ============================================================
   공용 화면 부품 (책 무관) — 여러 화면 JS 가 함께 쓰는 것 한 벌.
   이 블록은 페이지에서 **가장 먼저** 주입된다(window.BP 를 뒤 블록들이 읽는다).
   고치는 곳은 여기 하나다 — 예전엔 esc·칸 이름표·소절 정규식이 파일마다 복붙돼
   한쪽만 고치면 화면마다 달라졌다.
   ============================================================ */
(function(){
  'use strict';
  window.BP = {
    // HTML 특수문자 안전 출력 (& < > " 처리 + 빈값/널 보호)
    esc: function(s){
      return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },
    // 조건 칸(zone) 키 → 한글 이름표. 정본은 파이썬(dsl/tradeTool.ZONE_LABELS)이고 판정 JSON(#verdict-data 의
    //   VD.zones)으로 실려 온다 — 화면에 사본을 두지 않는다(주인 표: 칸·등급 이름표). 판정 JSON 이 없으면 키 그대로.
    zw: function(key){
      var vz = null;
      try { vz = (JSON.parse((document.getElementById('verdict-data')||{}).textContent || 'null') || {}).zones; } catch(e){}
      return (vz && vz[key]) || key;
    },
    // 소절 번호(예 "3-2"·"프롤로그"·"에필로그")를 머리에서 뽑는다 — group[1] = 소절 키
    REF_RE: /^\s*([0-9]+-[0-9]+|프롤로그|에필로그)/,
    // 플레이북 원문의 ### 소절 제목 줄 — group[1] = 소절 키, group[2] = 제목
    REF_HEAD_RE: /^#{3}\s*([0-9]+-[0-9]+|프롤로그|에필로그)[.\s]\s*(.*)$/
  };
})();
