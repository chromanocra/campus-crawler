import re
import datetime
from playwright.sync_api import sync_playwright

def solve_math_captcha(page):
    try:
        captcha_element = page.locator("text=/Berapa hasil dari/i")
        captcha_element.wait_for(timeout=5000)
        captcha_text = captcha_element.inner_text()
        
        numbers = re.findall(r'\d+', captcha_text)
        if len(numbers) >= 2:
            return str(int(numbers[0]) + int(numbers[1]))
        raise Exception("Format angka captcha tidak sesuai.")
    except Exception as e:
        raise Exception(f"Gagal bypass captcha: {str(e)}")

def is_waktu_kuliah(hari_jam_teks, hari_ini_id, jam_sekarang):
    try:
        if " - " not in hari_jam_teks:
            return False
            
        hari_matkul, jam_range = hari_jam_teks.split(" - ", 1)
        
        if hari_matkul.strip().lower() != hari_ini_id.lower():
            return False
            
        if "-" in jam_range:
            jam_mulai_str, jam_selesai_str = jam_range.split("-", 1)
            
            format_jam = "%H:%M"
            jam_mulai = datetime.datetime.strptime(jam_mulai_str.strip(), format_jam).time()
            jam_selesai = datetime.datetime.strptime(jam_selesai_str.strip(), format_jam).time()
            
            # Cek apakah jam sekarang berada di antara jam mulai dan jam selesai
            return jam_mulai <= jam_sekarang <= jam_selesai
    except Exception as e:
        print(f"[!] Gagal parsing waktu '{hari_jam_teks}': {e}")
    return False

def run_crawling(nim, password):
    """Fungsi utama otomasi absensi berdasarkan jadwal aktif"""
    
    # Ambil data waktu sekarang
    waktu_sekarang_dt = datetime.datetime.now()
    hari_ini_en = waktu_sekarang_dt.strftime("%A")
    jam_sekarang = waktu_sekarang_dt.time()
    
    kamus_hari = {
        "Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu",
        "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"
    }
    hari_ini_id = kamus_hari.get(hari_ini_en, hari_ini_en)
    
    status_report = {"status": "no_schedule", "message": "Tidak ada jadwal kuliah saat ini."}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            print("[*] Mengakses halaman login MyBest...")
            page.goto("https://elearning.bsi.ac.id/sch")
            
            page.get_by_placeholder("Masukkan NIP Dosen / NIM Mahasiswa").fill(nim)
            page.get_by_placeholder("Masukkan password").fill(password)
            
            jawaban_captcha = solve_math_captcha(page)
            page.get_by_placeholder("Jawaban").fill(jawaban_captcha)
            
            page.get_by_role("button", name="Masuk").click()
            
            # Tunggu login berhasil (Dashboard muncul)
            page.get_by_role("link", name="Dashboard").wait_for(timeout=15000)
            print("[+] Login berhasil!")

            # --- NAVIGASI KE MENU JADWAL ---
            print("[*] Memeriksa sidebar menu...")
            tombol_sidebar = page.locator("#toggle-sidebar")
            
            if tombol_sidebar.is_visible():
                print("[*] Membuka sidebar yang tersembunyi...")
                tombol_sidebar.click()
                page.wait_for_timeout(1000) # Jeda agar animasi selesai
            
            print("[*] Mengklik menu Jadwal...")
            page.get_by_text("Jadwal", exact=True).click()
            
            # Tunggu sampai kartu matkul di halaman Jadwal muncul
            page.locator(".pricing-plan").first.wait_for(timeout=15000)

            # --- FILTERING KARTU JADWAL ---
            cards = page.locator(".pricing-plan")
            total_cards = cards.count()
            print(f"[*] Menemukan {total_cards} kartu matakuliah di halaman jadwal.")

            for i in range(total_cards):
                card = cards.nth(i)
                
                # Mengambil text nama matkul dan info waktu (.pricing-title & .pricing-save)
                matkul_element = card.locator(".pricing-title")
                waktu_element = card.locator(".pricing-save")
                
                if not matkul_element.count() or not waktu_element.count():
                    continue
                    
                nama_matkul = matkul_element.inner_text().strip()
                hari_jam_teks = waktu_element.inner_text().strip()
                
                print(f"    -> Memeriksa: {nama_matkul} ({hari_jam_teks})")
                
                # Jalankan fungsi filter waktu
                if is_waktu_kuliah(hari_jam_teks, hari_ini_id, jam_sekarang):
                    print(f"[!] JADWAL COCOK! Mencoba masuk ke kelas: {nama_matkul}")
                    
                    # Cari tombol "Masuk Kelas" yang berada DI DALAM kartu spesifik ini saja
                    tombol_masuk = card.get_by_role("link", name="Masuk Kelas")
                    
                    if tombol_masuk.count() > 0:
                        tombol_masuk.click()
                        
                        # --- EKSEKUSI FORM ABSENSI ---
                        print("[*] Menunggu halaman absensi termuat...")
                        page.get_by_text("Jam Masuk").wait_for(timeout=10000)
                        
                        # Cek apakah form absen "Pengajaran Sesuai" tersedia di halaman
                        radio_absen = page.get_by_text("Pengajaran Sesuai")
                        if radio_absen.count() > 0:
                            radio_absen.click()
                            page.get_by_role("button", name="Kirim").click()
                            print(f"[+] Berhasil melakukan absensi untuk {nama_matkul}!")
                            
                            status_report = {
                                "status": "success",
                                "matkul": nama_matkul,
                                "message": f"Berhasil absen otomatis matkul {nama_matkul}."
                            }
                        else:
                            print("[-] Form absensi tidak ditemukan. Mungkin Anda sudah melakukan absen sebelumnya.")
                            status_report = {
                                "status": "already_done",
                                "matkul": nama_matkul,
                                "message": f"Form tidak ditemukan, kemungkinan sudah absen untuk matkul {nama_matkul}."
                            }
                        break 
                    else:
                        print(f"[-] Tombol 'Masuk Kelas' tidak aktif/tidak ada pada matkul {nama_matkul}.")
            
        except Exception as e:
            print(f"[!] Terjadi Error: {str(e)}")
            status_report = {"status": "failed", "message": str(e)}
            
        finally:
            browser.close()
            
    return status_report

if __name__ == "__main__":
    res = run_crawling("15240640", "Rizky-45")
    print("Hasil Akhir:", res)