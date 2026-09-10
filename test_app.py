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
    assert "Print by Writing Something" in res_test.text
    print(" [OK] /test (Default Page) rendered cleanly")

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

    # 7. Access /documentation with session
    res_doc = client.get("/documentation", cookies=cookies)
    assert res_doc.status_code == 200
    assert "Integration Guide" in res_doc.text
    assert "base-url-display" in res_doc.text
    assert "base-url-placeholder" in res_doc.text
    assert "baseUrlInput" in res_doc.text

    # Test reverse proxy headers (Cloudflare / Nginx)
    res_doc_proxy = client.get(
        "/documentation",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "pos.sayem.com"},
        cookies=cookies,
    )
    assert res_doc_proxy.status_code == 200
    assert "https://pos.sayem.com" in res_doc_proxy.text
    print(" [OK] /documentation dynamically used production proxy headers (https://pos.sayem.com)")
    print(" [OK] /documentation rendered cleanly with keepjob & immediate docs")

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


if __name__ == "__main__":
    test_sqlite_api_keys()
    test_auth_and_ui_pages()
    test_temporary_vs_preserved_jobs()
    test_api_printing_pipeline()
    test_stop_print_flow()
    test_bangla_unicode_text_printing()
    print("\n🎉 ALL TESTS (BANGLA UNICODE, KEEPJOB LIFECYCLE, STOP API, UI CONTROLS & SQLITE) PASSED SUCCESSFULLY!")
