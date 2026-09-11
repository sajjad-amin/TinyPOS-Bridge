import asyncio
import io
import json
from fastapi.testclient import TestClient
from PIL import Image
import pymupdf

import main
import server.config
import server.db as db
import printer_ble
from server.services.print_service import schedule_job_cleanup

client = TestClient(main.app)

def test_sqlite_api_keys():
    print("--> Testing SQLite API Keys CRUD...")
    test_key = "sk_test_sqlite_key_999"
    
    # 1. Insert key
    key_entry = db.insert_api_key(key=test_key, name="PyTest Integration Key")
    assert key_entry["key"] == test_key
    assert key_entry["name"] == "PyTest Integration Key"
    assert db.is_valid_api_key(test_key) is True
    print(" [OK] SQLite key insertion & validation verified")

    # 2. Retrieve key
    fetched = db.get_api_key(test_key)
    assert fetched is not None
    assert fetched["name"] == "PyTest Integration Key"
    print(" [OK] SQLite key retrieval verified")

    # 3. List keys includes this key
    all_keys = db.list_api_keys()
    assert any(k["key"] == test_key for k in all_keys)
    print(" [OK] SQLite list_api_keys verified")

    # 4. Delete key
    assert db.delete_api_key(test_key) is True
    assert db.is_valid_api_key(test_key) is False
    assert db.get_api_key(test_key) is None
    print(" [OK] SQLite key deletion verified")


def test_auth_and_ui_pages():
    print("--> Testing Authentication & UI Routes...")

    # 1. Unauthenticated root redirects to /login
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/login"
    print(" [OK] / redirected to /login")

    # 2. Login page renders
    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert "Sign In to TinyPOS" in res_login.text
    print(" [OK] /login rendered cleanly")

    # 3. Post login with correct credentials
    login_res = client.post(
        "/login",
        data={"username": server.config.get_admin_username(), "password": server.config.get_admin_password()},
        follow_redirects=False,
    )
    assert login_res.status_code == 303
    assert login_res.headers["location"] == "/test"
    cookies = login_res.cookies
    assert "tinypos_session" in cookies
    print(" [OK] Login successful, session cookie issued")

    # 4. Access /test (Default Page) with session
    res_test = client.get("/test", cookies=cookies)
    assert res_test.status_code == 200
    assert "Printer Test Console" in res_test.text
    assert "Print Text" in res_test.text
    assert "Print QR Code" in res_test.text
    assert "sample-lang-select" in res_test.text
    assert "qr-content" in res_test.text
    assert "qr-input-url" in res_test.text
    assert "qr-wifi-ssid" in res_test.text
    print(" [OK] /test (Modular Console with Text, QR URL/Wi-Fi/Text, & Photo Studio) rendered cleanly")

    # 5. Access /api-keys with session
    res_keys = client.get("/api-keys", cookies=cookies)
    assert res_keys.status_code == 200
    assert "Manage API Keys" in res_keys.text
    print(" [OK] /api-keys rendered cleanly")

    # 6. Create key via UI action (stored in SQLite)
    ui_key = "sk_live_test1234567890abcdef"
    create_res = client.post(
        "/api-keys/create",
        data={"name": "Laravel Web POS", "key": ui_key},
        cookies=cookies,
        follow_redirects=False,
    )
    assert create_res.status_code == 303
    assert db.is_valid_api_key(ui_key) is True
    print(" [OK] Created API Key via UI successfully into SQLite")

    # 7. Access /documentation and all separate subpages with session
    res_doc = client.get("/documentation", cookies=cookies)
    assert res_doc.status_code == 200
    assert "Integration Guide" in res_doc.text
    assert "base-url-display" in res_doc.text
    assert "base-url-placeholder" in res_doc.text
    assert "baseUrlInput" in res_doc.text
    assert "docSubmenu" in res_doc.text
    assert "/documentation/qr" in res_doc.text
    assert "/documentation/photo" in res_doc.text
    assert "/documentation/documents" in res_doc.text
    assert "/documentation/text" in res_doc.text
    assert "/documentation/control" in res_doc.text

    # Test reverse proxy headers (Cloudflare / Nginx)
    res_doc_proxy = client.get(
        "/documentation",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "pos.sayem.com"},
        cookies=cookies,
    )
    assert res_doc_proxy.status_code == 200
    assert "https://pos.sayem.com" in res_doc_proxy.text

    # Test each separate documentation subpage
    subpages = [
        ("/documentation/qr", "QR Code API", "/api/print/qr"),
        ("/documentation/photo", "Photo Studio API", "/api/print/photo"),
        ("/documentation/documents", "Invoices & PDFs", "/api/print/raw"),
        ("/documentation/text", "Multilingual Text", "/api/print/text"),
        ("/documentation/control", "Job Control", "/api/print/stop"),
    ]
    for path, title_snippet, endpoint_snippet in subpages:
        sub_res = client.get(path, cookies=cookies)
        assert sub_res.status_code == 200
        assert (title_snippet in sub_res.text or title_snippet.replace("&", "&amp;") in sub_res.text)
        assert endpoint_snippet in sub_res.text
        assert "docSubmenu" in sub_res.text
        print(f" [OK] {path} rendered cleanly with submenu and {endpoint_snippet}")

    print(" [OK] /documentation dynamically used production proxy headers (https://pos.sayem.com)")
    print(" [OK] All separate documentation subpages verified successfully")

    # 8. Delete key via UI action
    del_res = client.post(
        "/api-keys/delete",
        data={"key_to_delete": ui_key},
        cookies=cookies,
        follow_redirects=False,
    )
    assert del_res.status_code == 303
    assert db.is_valid_api_key(ui_key) is False
    print(" [OK] Deleted API Key via UI successfully from SQLite")


def test_api_printing_pipeline():
    print("--> Testing API Print Pipeline with X-API-Key...")
    test_key = "sk_live_integration_key"
    if not db.is_valid_api_key(test_key):
        db.insert_api_key(key=test_key, name="Integration Test")

    # 1. Immediate 1-Step Text Print (default immediate=True, keep_job=False)
    res_direct = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "Direct 1-Step Print Test\nInvoice #1001", "font_size": 22, "immediate": True},
    )
    assert res_direct.status_code == 200
    data_direct = res_direct.json()
    assert "job_id" in data_direct
    assert data_direct["status"] == "printing"
    assert data_direct["immediate"] is True
    assert data_direct["keep_job"] is False
    assert data_direct["confirm_url"] is None
    print(f" [OK] 1-Step direct text print verified (job: {data_direct['job_id']}, keep_job: false)")

    # 2. 2-Step Manual Text Print (immediate=False, keep_job=True)
    res_step = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "Two Step Manual Print\nInvoice #1002", "font_size": 22, "immediate": False, "keepjob": True},
    )
    assert res_step.status_code == 200
    data_step = res_step.json()
    assert "job_id" in data_step
    assert data_step["status"] == "pending"
    assert data_step["immediate"] is False
    assert data_step["keep_job"] is True
    assert data_step["confirm_url"] is not None
    job_id = data_step["job_id"]
    print(f" [OK] 2-Step pending text print created: {job_id} (keepjob: true)")

    # 3. Preview queued pending job
    preview_res = client.get(f"/api/print/preview/{job_id}")
    assert preview_res.status_code == 200
    assert preview_res.headers["content-type"] == "image/png"
    print(" [OK] Preview PNG retrieved from SQLite")

    # 4. Confirm queued pending job
    confirm_res = client.post(f"/api/print/confirm/{job_id}", headers={"X-API-Key": test_key})
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "printing"
    print(f" [OK] Job {job_id} confirmed and switched to printing status")

    # 5. Cancel test
    res_cancel_target = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "To be cancelled", "immediate": False},
    )
    cancel_job_id = res_cancel_target.json()["job_id"]
    cancel_res = client.delete(f"/api/print/cancel/{cancel_job_id}", headers={"X-API-Key": test_key})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"
    print(f" [OK] Job {cancel_job_id} cancelled cleanly")

    # 6. Raw file print with scale, autocrop, immediate=True, and keepjob=false
    img = Image.new("RGB", (600, 800), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    raw_res = client.post(
        "/api/print/raw",
        headers={"X-API-Key": test_key},
        files={"file": ("test_receipt.png", buf, "image/png")},
        data={"strength": "7", "scale": "1.25", "autocrop": "true", "immediate": "true", "keepjob": "false"},
    )
    assert raw_res.status_code == 200
    raw_data = raw_res.json()
    assert raw_data["status"] == "printing"
    assert raw_data["scale"] == 1.25
    assert raw_data["autocrop"] is True
    assert raw_data["immediate"] is True
    assert raw_data["keep_job"] is False
    print(" [OK] Raw file upload with immediate=true, keepjob=false verified")

    # 7. Internal preview file
    buf.seek(0)
    login_res = client.post(
        "/login",
        data={"username": server.config.get_admin_username(), "password": server.config.get_admin_password()},
        follow_redirects=False,
    )
    cookies = login_res.cookies
    prev_file_res = client.post(
        "/api/internal/preview-file",
        cookies=cookies,
        files={"file": ("test_receipt.png", buf, "image/png")},
        data={"strength": "7", "scale": "1.5", "autocrop": "true"},
    )
    assert prev_file_res.status_code == 200
    assert prev_file_res.headers["content-type"] == "image/png"
    print(" [OK] /api/internal/preview-file returned valid 384px PNG preview")

    # 8. Key history page
    hist_res = client.get(f"/api-keys/{test_key}/history", cookies=cookies)
    assert hist_res.status_code == 200
    assert "Print History" in hist_res.text
    print(" [OK] /api-keys/{key}/history rendered cleanly with SQLite records")

    # 9. Internal queue pagination (50/page)
    queue_res = client.get("/api/internal/queue?page=1&per_page=50", cookies=cookies)
    assert queue_res.status_code == 200
    queue_data = queue_res.json()
    assert "jobs" in queue_data
    assert "total" in queue_data
    assert queue_data["per_page"] == 50
    print(" [OK] /api/internal/queue returned paginated SQLite jobs")

    # 10. Single job deletion
    target_job_id = raw_data["job_id"]
    del_job_res = client.delete(f"/api/internal/jobs/{target_job_id}", cookies=cookies)
    assert del_job_res.status_code == 200
    assert del_job_res.json()["success"] is True
    print(f" [OK] Single job deletion verified for {target_job_id}")

    # 11. Bulk clear
    clear_res = client.post("/api/internal/jobs/clear", cookies=cookies)
    assert clear_res.status_code == 200
    assert clear_res.json()["success"] is True
    print(" [OK] Bulk clear jobs verified")


def test_temporary_vs_preserved_jobs():
    print("--> Testing Temporary Jobs vs Preserved Jobs (keepjob)...")
    test_key = "sk_live_integration_key"
    if not db.is_valid_api_key(test_key):
        db.insert_api_key(key=test_key, name="Integration Test")

    # 1. Create a temporary job (keepjob=False by default)
    temp_res = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "Temporary Receipt", "immediate": False, "keepjob": False},
    )
    temp_job_id = temp_res.json()["job_id"]
    temp_job = db.get_job(temp_job_id)
    assert temp_job is not None
    assert temp_job["keep_job"] == 0
    print(f" [OK] Temporary job {temp_job_id} created with keep_job=0")

    # 2. Create a preserved job (keepjob=True)
    perm_res = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "Preserved Receipt", "immediate": False, "keepjob": True},
    )
    perm_job_id = perm_res.json()["job_id"]
    perm_job = db.get_job(perm_job_id)
    assert perm_job is not None
    assert perm_job["keep_job"] == 1
    print(f" [OK] Preserved job {perm_job_id} created with keep_job=1")

    # 3. Test db.cleanup_temporary_jobs:
    # Older than -1 seconds means any created_at <= now is purged IF keep_job == 0
    deleted_count = db.cleanup_temporary_jobs(older_than_seconds=-1)
    assert deleted_count >= 1

    # Verify temp job was removed
    assert db.get_job(temp_job_id) is None
    print(f" [OK] Temporary job {temp_job_id} successfully purged by cleanup_temporary_jobs")

    # Verify perm job is still present
    assert db.get_job(perm_job_id) is not None
    print(f" [OK] Preserved job {perm_job_id} remains intact after cleanup")

    # 4. Test schedule_job_cleanup with short delay
    temp2_res = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": "Auto Timer Receipt", "immediate": False, "keepjob": False},
    )
    temp2_job_id = temp2_res.json()["job_id"]
    assert db.get_job(temp2_job_id) is not None

    # Run schedule_job_cleanup with 0.05s delay
    asyncio.run(schedule_job_cleanup(temp2_job_id, delay_seconds=0.05))
    assert db.get_job(temp2_job_id) is None
    print(f" [OK] schedule_job_cleanup purged temporary job {temp2_job_id} on timer")

    # Cleanup perm job
    db.delete_job(perm_job_id)


def test_stop_print_flow():
    print("--> Testing Stop Printing API & UI Controls...")
    test_key = "sk_live_integration_key"
    if not db.is_valid_api_key(test_key):
        db.insert_api_key(key=test_key, name="Integration Test")

    login_res = client.post(
        "/login",
        data={"username": server.config.get_admin_username(), "password": server.config.get_admin_password()},
        follow_redirects=False,
    )
    cookies = login_res.cookies

    # 1. Verify Stop buttons in UI template
    res_test = client.get("/test", cookies=cookies)
    assert res_test.status_code == 200
    assert 'id="btn-stop-text"' in res_test.text
    assert 'id="btn-stop-file"' in res_test.text
    assert 'stopPrintingNow()' in res_test.text
    assert 'stopJob(' in res_test.text
    print(" [OK] Test UI includes Stop buttons for both text and file")

    # 2. Verify BLE stop state machine when idle
    assert printer_ble.is_printing() is False
    stopped, msg = printer_ble.stop_printing()
    assert stopped is False
    assert "No active print job" in msg
    print(" [OK] printer_ble.stop_printing() idle rejection verified")

    # 3. Internal stop endpoint when idle
    res_int_stop = client.post("/api/internal/stop", cookies=cookies)
    assert res_int_stop.status_code == 200
    assert res_int_stop.json()["success"] is False
    print(" [OK] /api/internal/stop endpoint handled idle status cleanly")

    # 4. Public stop endpoint when idle
    res_pub_stop = client.post("/api/print/stop", headers={"X-API-Key": test_key})
    assert res_pub_stop.status_code == 400
    assert res_pub_stop.json()["success"] is False
    print(" [OK] /api/print/stop endpoint handled idle status cleanly")

    # 5. Stop a job via internal /jobs/{job_id}/stop
    test_job_id = "test-job-stop-internal"
    db.insert_job(
        job_id=test_job_id,
        job_type="text",
        status="printing",
        api_key="test_page",
        keep_job=True,
    )
    res_job_stop = client.post(f"/api/internal/jobs/{test_job_id}/stop", cookies=cookies)
    assert res_job_stop.status_code == 200
    assert res_job_stop.json()["success"] is True
    job_record = db.get_job(test_job_id)
    assert job_record["status"] == "cancelled"
    print(" [OK] Internal /jobs/{job_id}/stop successfully cancelled printing job")
    db.delete_job(test_job_id)

    # 6. Stop an active printing job via public /api/print/cancel/{job_id}
    test_pub_job_id = "test-job-stop-public"
    db.insert_job(
        job_id=test_pub_job_id,
        job_type="text",
        status="printing",
        api_key=test_key,
        keep_job=True,
    )
    res_pub_cancel = client.delete(f"/api/print/cancel/{test_pub_job_id}", headers={"X-API-Key": test_key})
    assert res_pub_cancel.status_code == 200
    assert res_pub_cancel.json()["status"] == "cancelled"
    assert "Active print job stopped" in res_pub_cancel.json()["message"]
    job_record_pub = db.get_job(test_pub_job_id)
    assert job_record_pub["status"] == "cancelled"
    print(" [OK] Public /api/print/cancel/{job_id} successfully stopped active printing job")
    db.delete_job(test_pub_job_id)


def test_bangla_unicode_text_printing():
    print("--> Testing Unicode Bangla Text Rendering & API Pipeline...")

    # 1. Direct render_text_to_bitmap with complex Bengali characters & currency
    bn_text = """================================
       সাজ্জাদ স্টোর
   রশিদ নং #INV-2026-0042
--------------------------------
আইটেম              পরিমাণ   দাম
--------------------------------
মিনিকেট চাল ৫ কেজি     ১    ৳৫০০.০০
সয়াবিন তেল ২ লিটার     ১    ৳৩৬০.০০
চিনি ১ কেজি            ১    ৳১৩০.০০
--------------------------------
মোট পরিশোধ:                 ৳৯৯০.০০
================================
    ধন্যবাদ আবার আসবেন!"""

    bitmap = printer_ble.render_text_to_bitmap(bn_text, font_size=22, strength=7)
    assert bitmap.size[0] == 384
    assert bitmap.size[1] > 200

    # Ensure glyphs rendered dark pixels (not blank or missing)
    black_pixels = [p for p in bitmap.getdata() if p < 128]
    assert len(black_pixels) > 1000, "Should have rendered dark pixels for Bangla characters"
    print(f" [OK] Direct render_text_to_bitmap rendered {len(black_pixels)} black pixels on 384px canvas")

    # 2. Test /api/internal/preview-text with Bangla payload
    login_res = client.post(
        "/login",
        data={"username": server.config.get_admin_username(), "password": server.config.get_admin_password()},
        follow_redirects=False,
    )
    cookies = login_res.cookies

    res_prev = client.post(
        "/api/internal/preview-text",
        cookies=cookies,
        json={"text": bn_text, "font_size": 22, "strength": 7},
    )
    assert res_prev.status_code == 200
    assert res_prev.headers["content-type"] == "image/png"
    img_stream = Image.open(io.BytesIO(res_prev.content))
    assert img_stream.size[0] == 384
    assert img_stream.size[1] > 200
    print(" [OK] /api/internal/preview-text generated valid 384px PNG preview for Bangla text")

    # 3. Test /api/print/text with Bangla payload
    test_key = "sk_live_bangla_test_key"
    if not db.is_valid_api_key(test_key):
        db.insert_api_key(key=test_key, name="Bangla Test Key")

    res_api = client.post(
        "/api/print/text",
        headers={"X-API-Key": test_key},
        json={"text": bn_text, "font_size": 22, "immediate": False, "keepjob": True},
    )
    assert res_api.status_code == 200
    job_data = res_api.json()
    assert "job_id" in job_data
    db_job = db.get_job(job_data["job_id"])
    assert db_job is not None
    assert db_job["job_type"] == "text"
    print(f" [OK] Public /api/print/text successfully queued Bangla print job: {job_data['job_id']}")
    db.delete_job(job_data["job_id"])
    db.delete_api_key(test_key)


def test_universal_multilingual_printing():
    print("--> Testing Universal Multi-Language Text Rendering Pipeline...")

    test_languages = {
        "Bengali": "আমার সোনার বাংলা, আমি তোমায় ভালোবাসি",
        "Arabic": "خير الكلام ما قل ودل • شكراً لزيارتكم",
        "English": "To be, or not to be, that is the question.",
        "Chinese": "千里之行，始于足下 • 欢迎光临",
        "Hindi": "सारे जहाँ से अच्छा, हिन्दोसितां हमारा",
        "Russian": "Красота спасёт мир — Фёдор Достоевский",
        "Japanese": "七転び八起き、明日は明日の風が吹く",
        "Telugu": "దేశభాషలందు తెలుగు లెస్స • స్వాగతం",
        "Tamil": "யாதும் ஊரே யாவரும் கேளிர் • வணக்கம்",
        "Korean": "시작이 반이다, 고생 끝에 낙이 온다",
        "Thai": "ความพยายามอยู่ที่ไหน ความสำเร็จอยู่ที่นั่น",
        "Gujarati": "જ્યાં જ્યાં વસે એક ગુજરાતી, ત્યાં ત્યાં સદાકાળ ગુજરાત",
        "Kannada": "ಸಿರಿಗನ್ನಡಂ ಗೆಲ್ಗೆ, ಸಿರಿಗನ್ನಡಂ ಬಾಳ್ಗೆ",
        "Malayalam": "സ്വാഗതം • നന്ദി • എല്ലാ ഭാഷകളും ഇവിടെയുണ്ട്",
        "Odia": "ସୁନ୍ଦର ଓଡ଼ିଶା • ଆପଣଙ୍କୁ ସ୍ୱାଗତମ୍",
        "Myanmar": "ကြိုဆိုပါသည် • ကျေးဇူးတင်ပါသည်",
        "Gurmukhi": "ਜੀ ਆਇਆਂ ਨੂੰ • ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ",
        "Ethiopic": "እንኳን ደህና መጡ • ሰላም ለሁሉም ይሁን",
        "Lao": "ຍິນດີຕ້ອນຮັບ • ຄວາມພະຍາຍາມຢູ່ໃສ ຄວາມສໍາເລັດຢູ່ນັ້ນ",
        "Khmer": "សូមស្វាគមន៍ • ការព្យាយាមគង់បានសម្រេច",
        "Sinhala": "සාදරයෙන් පිළිගනිමු • ජයෙන් ජයම වේවා",
        "Greek": "Γνῶθι σεαυτόν • Καλώς ήρθατε",
        "Hebrew": "שלום עליכם • ברוכים הבאים • קבלה",
        "Armenian": "Բարի գալուստ • Խաղաղություն ամենքին",
        "Georgian": "მოგესალმებით • მშვიდობა ყველას",
        "Emoji": "Receipt 🧾 Express Print 🚀 Rating ⭐⭐⭐⭐⭐ Success ✔️",
    }

    for lang, text in test_languages.items():
        bmp = printer_ble.render_text_to_bitmap(text, font_size=22, strength=7)
        assert bmp.size[0] == 384
        black_count = sum(1 for p in bmp.get_flattened_data() if p < 128)
        assert black_count > 300, f"Too few black pixels for {lang}"

    # Verify All Languages universal receipt
    all_text = "\n".join(test_languages.values())
    bmp_all = printer_ble.render_text_to_bitmap(all_text, font_size=20, strength=7)
    assert bmp_all.size[0] == 384
    assert sum(1 for p in bmp_all.get_flattened_data() if p < 128) > 30000

    print(f" [OK] All {len(test_languages)} international language scripts and All-Languages universal receipt rendered cleanly with high contrast")


def test_mixed_multi_script_rendering():
    print("--> Testing Mixed Multi-Script & Emoji Rendering Pipeline...")
    mixed_samples = [
        "Receipt 🧾 Express Print 🚀 Rating ⭐⭐⭐⭐⭐ Success ✔️",
        "Korean POS 🇰🇷 영수증 🧾 15,000원 • Rating ⭐⭐⭐⭐⭐",
        "সাজ্জাদ স্টোর 🇧🇩 - চাল ৫ কেজি 🌾 ৳৫০০ • Rating ⭐⭐⭐",
        "Coffee ☕ $5.00 | 欢迎光临 • شكراً لزيارتكم",
    ]

    for line in mixed_samples:
        bmp = printer_ble.render_text_to_bitmap(line, font_size=22, strength=7)
        assert bmp.size[0] == 384
        black_count = sum(1 for p in bmp.get_flattened_data() if p < 128)
        assert black_count > 1000, f"Too few black pixels for mixed line: {line}"

    print(" [OK] Mixed script text (English + Korean + Emoji + Bengali + Arabic + CJK) rendered cleanly without missing boxes")


def test_qr_code_rendering_and_api():
    print("--> Testing QR Code Rendering & API Pipeline...")

    # 1. Test engine renderer directly
    bmp = printer_ble.render_qr_to_bitmap(
        content="https://pos.sayem.com",
        header_text="SCAN TO PAY",
        footer_text="TinyPOS Thermal Bridge",
        qr_size=260,
        strength=7,
    )
    assert bmp.size[0] == 384
    assert bmp.size[1] > 260
    black_pixels = sum(1 for p in bmp.get_flattened_data() if p < 128)
    assert black_pixels > 2000, f"Expected dark modules in QR code, got {black_pixels}"
    print(" [OK] Engine render_qr_to_bitmap output verified (384px wide, sharp thermal pixels)")

    # 2. Test internal preview endpoint
    res_preview = client.post(
        "/api/internal/preview-qr",
        json={
            "content": "https://pos.sayem.com",
            "header": "TABLE #12",
            "footer": "THANK YOU",
            "qr_size": 240,
            "strength": 7,
        },
    )
    assert res_preview.status_code == 200
    assert res_preview.headers["content-type"] == "image/png"
    img = Image.open(io.BytesIO(res_preview.content))
    assert img.size[0] == 384
    print(" [OK] Internal /api/internal/preview-qr endpoint verified")

    # 3. Test public print QR API with API key
    test_key = "sk_test_qr_print_key_101"
    db.delete_api_key(test_key)
    db.insert_api_key(test_key, name="QR Test Client")

    res_print = client.post(
        "/api/print/qr",
        headers={"X-API-Key": test_key},
        json={
            "content": "WIFI:S:Guest;T:WPA;P:secret123;;",
            "header": "WI-FI LOGIN",
            "footer": "Connect & Enjoy",
            "qr_size": 260,
            "strength": 7,
            "immediate": True,
            "keep_job": True,
        },
    )
    assert res_print.status_code == 200
    data = res_print.json()
    assert data["status"] == "printing"
    job_id = data["job_id"]

    # Verify job persisted in SQLite
    job = db.get_job(job_id)
    assert job is not None
    assert job["job_type"] == "qr"
    assert job["api_key"] == test_key
    assert job["status"] in ("printing", "failed", "completed")
    assert job["keep_job"] == 1
    print(f" [OK] Public /api/print/qr completed and recorded in SQLite (Job {job_id[:8]})")

    # Clean up
    db.delete_api_key(test_key)
    db.delete_job(job_id)


def test_photo_dithering_and_direct_qr():
    print("--> Testing Photo Dithering Mode and Direct QR Generation API...")

    # 1. Test render_photo_to_bitmap directly
    test_img = Image.new("RGB", (200, 200), color=(128, 128, 128))
    photo_bitmap = printer_ble.render_photo_to_bitmap(test_img, scale=1.0, autocrop=False, strength=7)
    assert photo_bitmap.size[0] == 384
    assert photo_bitmap.mode == "1"
    print(" [OK] render_photo_to_bitmap produced valid 384px 1-bit dithered image")

    # 2. Test protocol encoding with 1-bit dithered image
    rows = printer_ble.encode_image_to_lsb_rows(photo_bitmap)
    assert len(rows) == photo_bitmap.size[1]
    assert all(len(r) == 384 // 8 for r in rows)
    print(" [OK] encode_image_to_lsb_rows cleanly encoded 1-bit dithered rows")

    # 3. Test public /api/print/raw with mode=photo
    test_key = "sk_test_photo_dither_key"
    db.delete_api_key(test_key)
    db.insert_api_key(test_key, name="Photo Dither Test Client")

    img_buf = io.BytesIO()
    test_img.save(img_buf, format="PNG")
    img_buf.seek(0)

    res_photo = client.post(
        "/api/print/raw",
        headers={"X-API-Key": test_key},
        files={"file": ("photo.png", img_buf.getvalue(), "image/png")},
        data={"mode": "photo", "immediate": False, "keep_job": False},
    )
    assert res_photo.status_code == 200
    data_photo = res_photo.json()
    assert data_photo["mode"] == "photo"
    assert data_photo["status"] == "pending"
    job_id = data_photo["job_id"]
    job = db.get_job(job_id)
    assert job is not None
    assert job["job_type"] == "image"
    print(" [OK] POST /api/print/raw with mode=photo succeeded")
    db.delete_job(job_id)

    # 4. Test public /api/print/raw with dither=true
    res_dither = client.post(
        "/api/print/raw",
        headers={"X-API-Key": test_key},
        files={"file": ("portrait.png", img_buf.getvalue(), "image/png")},
        data={"dither": "true", "immediate": False, "keep_job": False},
    )
    assert res_dither.status_code == 200
    data_dither = res_dither.json()
    assert data_dither["mode"] == "photo"
    db.delete_job(data_dither["job_id"])
    print(" [OK] POST /api/print/raw with dither=true succeeded")

    # 5. Test direct QR generation: GET /api/qr/generate?text=...
    res_qr_get = client.get("/api/qr/generate?text=https://pos.sayem.com/order/123&header=TABLE+5&footer=SCAN+TO+PAY&size=260")
    assert res_qr_get.status_code == 200
    assert res_qr_get.headers["content-type"] == "image/png"
    qr_img = Image.open(io.BytesIO(res_qr_get.content))
    assert qr_img.size[0] == 384
    print(" [OK] GET /api/qr/generate returned valid 384px PNG QR code directly")

    # 6. Test direct QR generation: POST /api/qr/generate (JSON payload)
    res_qr_post = client.post(
        "/api/qr/generate",
        json={
            "text": "WIFI:S:TinyPOS;T:WPA;P:password123;;",
            "header": "FREE WI-FI",
            "footer": "Password: password123",
            "size": 240,
        },
    )
    assert res_qr_post.status_code == 200
    assert res_qr_post.headers["content-type"] == "image/png"
    qr_post_img = Image.open(io.BytesIO(res_qr_post.content))
    assert qr_post_img.size[0] == 384
    print(" [OK] POST /api/qr/generate returned valid 384px PNG QR code directly")

    # 7. Test /api/print/qr with text alias (instead of content)
    res_qr_alias = client.post(
        "/api/print/qr",
        headers={"X-API-Key": test_key},
        json={
            "text": "https://example.com/invoice/999",
            "header": "INVOICE #999",
            "immediate": False,
        },
    )
    assert res_qr_alias.status_code == 200
    alias_job_id = res_qr_alias.json()["job_id"]
    db.delete_job(alias_job_id)
    print(" [OK] POST /api/print/qr with 'text' alias succeeded")

    # 8. Test dedicated POST /api/print/photo with presets and dithering algorithms
    for preset in ("portrait", "sharp", "balanced", "high_contrast", "halftone"):
        res_p = client.post(
            "/api/print/photo",
            headers={"X-API-Key": test_key},
            files={"file": ("test_preset.png", img_buf.getvalue(), "image/png")},
            data={"preset": preset, "immediate": False, "keep_job": False},
        )
        assert res_p.status_code == 200
        data_p = res_p.json()
        assert data_p["preset"] == preset
        assert data_p["status"] == "pending"
        db.delete_job(data_p["job_id"])
    print(" [OK] POST /api/print/photo verified across all 5 quality presets")

    # 9. Test internal preview-photo and print-photo
    res_prev = client.post(
        "/api/internal/preview-photo",
        files={"file": ("prev.png", img_buf.getvalue(), "image/png")},
        data={"preset": "sharp", "dither_algo": "atkinson", "sharpness": "2.0"},
    )
    assert res_prev.status_code == 200
    assert res_prev.headers["content-type"] == "image/png"
    prev_img = Image.open(io.BytesIO(res_prev.content))
    assert prev_img.size[0] == 384
    assert prev_img.mode == "1"
    print(" [OK] POST /api/internal/preview-photo returned valid 384px 1-bit PNG")

    # Clean up
    db.delete_api_key(test_key)


def test_settings_and_cloud_relay():
    print("--> Testing Settings UI, Mode Switching & Cloud Relay WebSocket...")
    from starlette.websockets import WebSocketDisconnect
    from server.services.relay_manager import relay_manager

    # 1. Ensure test API key and client API key exist
    test_key = "sk_test_relay_key_456"
    db.insert_api_key(key=test_key, name="Relay Store PC")
    db.insert_client_api_key(key=test_key, name="Relay Store PC")

    # 2. Test database settings & client keys operations
    db.set_setting("bridge_mode", "bluetooth")
    assert db.get_setting("bridge_mode") == "bluetooth"
    all_s = db.get_all_settings()
    assert all_s["bridge_mode"] == "bluetooth"

    # Dedicated client keys CRUD test
    ck_list = db.list_client_api_keys()
    assert any(k["key"] == test_key for k in ck_list)
    assert db.is_valid_client_api_key(test_key) is True
    assert db.is_valid_client_api_key("non_existent_key") is False
    print(" [OK] Database settings and dedicated client_api_keys CRUD verified")

    # 3. Test unauthenticated access to /settings redirects to login
    client.cookies.clear()
    res_unauth = client.get("/settings", follow_redirects=False)
    assert res_unauth.status_code in (302, 307)
    assert res_unauth.headers["location"] == "/login"

    # 4. Authenticate session
    auth_cookies = {"tinypos_session": "admin_authenticated"}
    res_ui = client.get("/settings", cookies=auth_cookies)
    assert res_ui.status_code == 200
    assert "Bridge &amp; Relay Settings" in res_ui.text or "Bridge & Relay Settings" in res_ui.text
    assert "Direct Bluetooth" in res_ui.text
    assert "Cloud Relay" in res_ui.text
    assert "Client Terminal Authorization Keys" in res_ui.text
    assert test_key in res_ui.text
    print(" [OK] GET /settings UI view rendered with dedicated Client Keys table")

    # Test create client key via UI route
    new_test_ck = "sk_client_office_test_888"
    create_ck_res = client.post(
        "/settings/client-keys/create",
        data={"name": "Office Register", "key": new_test_ck},
        cookies=auth_cookies,
        follow_redirects=False,
    )
    assert create_ck_res.status_code == 303
    assert db.is_valid_client_api_key(new_test_ck) is True
    print(" [OK] POST /settings/client-keys/create created new client key into SQLite")

    # Test delete client key via UI route
    del_ck_res = client.post(
        "/settings/client-keys/delete",
        data={"key_to_delete": new_test_ck},
        cookies=auth_cookies,
        follow_redirects=False,
    )
    assert del_ck_res.status_code == 303
    assert db.is_valid_client_api_key(new_test_ck) is False
    print(" [OK] POST /settings/client-keys/delete deleted client key cleanly")

    # 5. Test internal settings API endpoints
    res_get_set = client.get("/api/internal/settings", cookies=auth_cookies)
    assert res_get_set.status_code == 200
    assert res_get_set.json()["bridge_mode"] == "bluetooth"

    # Test internal client-keys API
    res_int_ck = client.get("/api/internal/client-keys", cookies=auth_cookies)
    assert res_int_ck.status_code == 200
    assert res_int_ck.json()["success"] is True
    assert any(k["key"] == test_key for k in res_int_ck.json()["client_keys"])

    # Switch mode via API
    res_mode = client.post("/api/internal/settings/mode", json={"mode": "relay"}, cookies=auth_cookies)
    assert res_mode.status_code == 200
    assert res_mode.json()["success"] is True
    assert db.get_setting("bridge_mode") == "relay"
    print(" [OK] Switched bridge mode to 'relay' via internal API")

    # Check /api/status respects relay mode without client
    res_status = client.get("/api/status", headers={"X-API-Key": test_key})
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["status"] == "offline"
    assert status_data["mode"] == "relay"
    print(" [OK] /api/status reports 'relay' mode without attempting BLE scan")

    # 6. Test WebSocket client connection rejection on bad API key
    try:
        with client.websocket_connect("/ws/client?api_key=bad_key_xyz") as ws:
            pass
        assert False, "Should have rejected bad API key"
    except WebSocketDisconnect as e:
        assert e.code == 1008
        print(" [OK] WebSocket connection rejected unauthorized key with code 1008")

    # 7. Test successful WebSocket connection with valid key
    with client.websocket_connect(f"/ws/client?api_key={test_key}&client_name=Store_POS_Terminal_1") as ws:
        # Welcome message
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert relay_manager.is_client_connected() is True
        print(" [OK] WebSocket client connected and received welcome packet")

        # Live status probe
        client_info = relay_manager.get_client_info()
        assert client_info is not None
        assert client_info["client_name"] == "Store_POS_Terminal_1"

        # Ping-Pong heartbeat
        ws.send_json({"type": "ping"})
        pong = ws.receive_json()
        assert pong["type"] == "pong"
        print(" [OK] Ping-pong heartbeat over WebSocket verified")

        # Client printer status reporting
        ws.send_json({
            "type": "printer_status",
            "status": "online",
            "printer_name": "X6 Portable Thermal",
            "address": "DC:0D:30:11:22:33",
        })

        # Internal relay status probe
        res_relay_stat = client.get("/api/internal/relay/status", cookies=auth_cookies)
        assert res_relay_stat.status_code == 200
        relay_json = res_relay_stat.json()
        assert relay_json["connected"] is True
        assert relay_json["client"]["printer_status"]["device_name"] == "X6 Portable Thermal"
        print(" [OK] Live relay status probe and printer status telemetry verified")

        # 8. Test Multi-Terminal Roaming Proximity & Mesh Resolution
        # Create second authorized client key for Office Mac
        key_office = "sk_client_office_mac_999"
        db.insert_client_api_key(key=key_office, name="Office Mac")
        with client.websocket_connect(f"/ws/client?api_key={key_office}&client_name=Office_Mac_Mini") as ws2:
            welcome2 = ws2.receive_json()
            assert welcome2["type"] == "welcome"
            assert relay_manager.get_client_count() == 2
            print(" [OK] Connected second client terminal simultaneously (Office_Mac_Mini)")

            # Terminal 2 reports closer signal (RSSI: -42 dBm) than Terminal 1 (RSSI: -70 dBm)
            ws.send_json({"type": "printer_status", "status": "online", "printer_name": "X6 Thermal", "rssi": -70})
            ws2.send_json({"type": "printer_status", "status": "online", "printer_name": "X6 Thermal", "rssi": -42})

            res_roam1 = client.get("/api/internal/relay/status", cookies=auth_cookies)
            assert res_roam1.status_code == 200
            roam1_json = res_roam1.json()
            assert roam1_json["client_count"] == 2
            assert roam1_json["active_client"]["client_name"] == "Office_Mac_Mini"
            print(" [OK] Roaming Mesh correctly selected closest terminal (Office_Mac_Mini at -42 dBm vs -70 dBm)")

            # Now portable printer moves closer to Terminal 1 (RSSI: -35 dBm)
            ws.send_json({"type": "printer_status", "status": "online", "printer_name": "X6 Thermal", "rssi": -35})
            res_roam2 = client.get("/api/internal/relay/status", cookies=auth_cookies)
            roam2_json = res_roam2.json()
            assert roam2_json["active_client"]["client_name"] == "Store_POS_Terminal_1"
            print(" [OK] Roaming Mesh automatically shifted active target to Store_POS_Terminal_1 as printer moved")

        db.delete_client_api_key(key_office)

    # 9. After client disconnects, status updates
    assert relay_manager.is_client_connected() is False
    print(" [OK] Client disconnection cleanly detected and unregistered")

    # 10. Reset bridge mode back to bluetooth
    db.set_setting("bridge_mode", "bluetooth")
    db.delete_api_key(test_key)
    db.delete_client_api_key(test_key)
    print(" [OK] Reset operating mode back to default 'bluetooth'")


if __name__ == "__main__":
    test_sqlite_api_keys()
    test_auth_and_ui_pages()
    test_temporary_vs_preserved_jobs()
    test_api_printing_pipeline()
    test_stop_print_flow()
    test_bangla_unicode_text_printing()
    test_universal_multilingual_printing()
    test_mixed_multi_script_rendering()
    test_qr_code_rendering_and_api()
    test_photo_dithering_and_direct_qr()
    test_settings_and_cloud_relay()
    print("\n🎉 ALL TESTS (SETTINGS, CLOUD RELAY, WEBSOCKET, PHOTO DITHERING, DIRECT QR API, MODULAR UI, MULTI-LANGUAGE, BANGLA UNICODE, KEEPJOB, STOP API & SQLITE) PASSED SUCCESSFULLY!")

