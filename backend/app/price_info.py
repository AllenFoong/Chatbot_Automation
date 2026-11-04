"""诊所的价目表（给 AI 回答价钱用；W64、D82）。

存在 clinic_settings.price_info，ADMIN 在 Settings → Prices 改；这里是第一版（2026-11-04 开发者给的价目表和员工平常的回复），
migration 0008 和 python -m app.db.seed 用它填进去。写英文，AI 用病人的语言回答。
"""

DEFAULT_PRICE_INFO = """\
All prices in RM. Ranges: the doctor decides the final price after checking.

1. Dental consultation / check-up 口腔检查: 20–50
2. Dental report 口腔报告: 150
3. Filling 补牙, per tooth: 100–160; baby tooth 90–130
4. Scaling & polishing 洗牙/抛光, one visit: 100–200; baby teeth 90–130
5. Tooth extraction 拔牙, per tooth: 100–200; baby tooth 90–130; difficult extraction 250–300
6. Wisdom tooth 智慧牙: price not confirmed yet. Say staff will reply about the price, and hand over.
7. Root canal treatment 牙根管治疗（抽牙根）, per tooth: 900–1300; baby tooth (pulpotomy) 500
8. Crown or bridge 牙冠/牙桥, per tooth: 1100–1500
9. Tooth whitening 牙齿美白, two ways:
   - At the clinic, blue light, one visit: 10 minutes 550; 20 minutes 750
   - At home: the doctor gives 8 tubes of gel and clear trays and shows how to use them: 1400.
     Most doctors suggest the home kit because it is gentler on the teeth. Kept in the fridge the gel lasts 2 years.
     Start one week before an important event: every night put the gel in the trays and sleep with them; it works in about a week.
10. Denture 假牙, normal, per arch: first tooth 850, each extra tooth +50, at most 1500 per arch.
    Cobalt chrome denture 1800. Valplast 950–1800.
11. Braces 绑牙 / orthodontic treatment, four kinds:
    - Normal braces 6000
    - Self-ligating braces 自动锁 7000
    - Ceramic braces 陶瓷牙套 8500
    - Invisalign 隐适美 19000–22000
    Included: impressions, X-ray and the retainer at the end. Not included: scaling, fillings, extractions or other treatment (paid separately).
    Braces: first payment 2000 (other treatment done at the start is added to it); then 200–500 at each monthly review until the balance is paid.
    Invisalign: first payment 2000; the doctor sends the case to the USA for a plan and discusses it with the patient;
    after the patient chooses a plan, 4000; at the first set of aligners, 4000; then 500–1000 at each monthly review.
    Monthly reviews (OR) and rebonding brackets (RB) during braces are part of these payments.
    For an exact price, invite the person to book a consultation: the doctor will explain.
12. Implant 植牙（种牙）, with guided bone regeneration: 6500–8000
13. Icon whitening, per tooth: 600
14. Hawley retainer 哈雷固定器 or soft mouth guard: 500 for one arch (for both arches: staff will reply)
15. Boxing mouth guard 厚款牙套: 1200
16. Functional appliance: 3000
17. Medication 药物: 60–100

Anything not in this list (insurance, discounts, other treatments): say staff will reply, and hand over.
"""
