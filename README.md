# ⚡ IEC 62056 TCP Elektrik Sayacı Simülatörü

Python ile yazılmış, **IEC 62056-21** (eski adıyla IEC 1107) protokolüne benzeyen, **TCP üzerinden çalışan** bir elektrik sayacı simülatörüdür.  
Gerçek ölçüm yapmaz; belirli periyotlarda (varsayılan **15 dk**) rastgele ama **pozitif ve tutarlı** tüketim üreterek hem:

- **Toplam tüketimi (OBIS 1.8.0)**,
- **Anlık gücü (1.7.0)**,
- **Gerilim değerini (32.7.0)**,
- **Yük profilini (P.01 kayıtları)**  

simüle eder ve bunları hem **TCP readout** olarak hem de **dosya** üzerinden sağlar.

> Bu repo, hem **gömülü cihaz geliştirenler** için bir test sayacı, hem de ileride eklenecek bir **UI için veri sağlayıcı backend** olarak tasarlanmıştır.

---

## 🛠 Özellikler

- **Katmanlı mimari**:
  - **Bağlantı katmanı**: TCP sunucu (`tcp_server.py`)
  - **Protokol / mesaj yorumlama**: IEC 62056 benzeri state machine (`iec62056_protocol.py`)
  - **Sayaç çekirdeği & yük profili**: Simülasyon ve veri dosyası yönetimi (`meter_model.py`)
- **Short / default readout** desteği:
  - `/?!` handshake → sayaç kimliği
  - `ACK050` → tam OBIS readout
- **Load profile (P.01)** sorgusu:
  - `P.01(YYMMDDhhmm)(YYMMDDhhmm)` → belirtilen aralıktaki kayıtlar
- **Yük profili dosyası**:
  - Varsayılan: `meter_data.txt`
  - Format: `P.01(YYMMDDhhmm)(vvvv.vv)`
  - Uygulama her açılışta bu dosyadan **1.8.0 toplamını yeniden hesaplar** → yük profili ile tutarlı toplam tüketim.
- **Kolay test için hızlandırılmış periyot**:
  - Gerçekte 15 dk, testte örn. 10 sn olarak ayarlanabilir.

- **🖥 TCP Client Uygulaması**:
  - TCP üzerinden bağlanma ve sorgulama
  - Host ve port parametreleri CLI ile ayarlanabilir
  - Timeout ve hata yönetimi ile güvenli bağlantı
  - OBIS readout
  - /?! → Sayaç kimliği alımı
  - ACK050 → Short/Full readout alma
  - Load profile (P.01) sorgusu
  - Başlangıç ve bitiş zaman aralığı ile veri çekme
  - Büyük veri desteği (buffer ≥ 4 KB)
  - **Parametreler**
    ```text
    --host, --port → Hedef sunucu
    --interval → Sorgulama periyodu (saniye cinsinden)
    --start, --end → Load profile zaman aralığı
    ```
    **Sürekli takip**
    - Belirlenen interval ile otomatik sorgulama
    - Ctrl+C ile güvenli durdurma
---

## ⚙ Kurulum

### 📦 Gereksinimler

- Python **3.9+** (3.10 veya üzeri tavsiye edilir)
- Windows, Linux veya macOS (örnekler Windows/PowerShell ile verilmiştir)

### 🚀 Çalıştırma

Projeyi klonladıktan sonra klasöre girin:

```bash
cd ElectricityMeter
```

Basit bir şekilde simülatörü başlatmak için:

```bash
python run_simulator.py
```

Varsayılan ayarlar:

- Host: `0.0.0.0`
- Port: `5000`
- Yük profili dosyası: `meter_data.txt`
- Periyot: `900` sn (**15 dk**)

Test için periyodu hızlandırmak isterseniz (örneğin her 10 sn’de bir yeni kayıt):

```bash
python run_simulator.py --interval-seconds 10
```

Özel port ve data dosyası örneği:

```bash
python run_simulator.py --host 127.0.0.1 --port 5000 --data-file data\my_meter.txt
```

Client ile bağlanmak ve verileri çekmek için:

```bash
python client.py --host 127.0.0.1 --port 5000 --interval 10
```

---

## 🧩Nasıl Çalışıyor? (Adım Adım)

### 1️⃣ Sayaç çekirdeği (MeterSimulator)

`meter_model.py` içindeki `MeterSimulator` sınıfı:

- Arka planda çalışan bir **thread** başlatır.
- Her periyotta (örn. 15 dk / 10 sn):
  - 0.1–0.6 kWh arası **rasgele pozitif tüketim** üretir.
  - Bu interval için ortalama güçten yola çıkarak **anlık güç (1.7.0)** değeri üretir.
  - 230 V civarında küçük bir oynama ile **gerilim (32.7.0)** üretir.
  - Bu tüketimi:
    - **Yük profiline (P.01 satırı)** ekler.
    - **Toplam tüketim 1.8.0** değerine ekler.
  - Yük profilini şu formatta dosyaya yazar:

```text
P.01(YYMMDDhhmm)(vvvv.vv)
Ör: P.01(2401010000)(0000.42)
```

- Uygulama her açıldığında:
  - `meter_data.txt` dosyasını okur,
  - Tüm satırlardaki tüketimleri toplayarak **1.8.0 toplamını yeniden hesaplar**.

### 2️⃣ Protokol akışı (IEC 62056 benzeri)

`iec62056_protocol.py` içindeki `ConnectionState`:

1. **Handshake**:
   - Client şu mesajı gönderir:
     - `/?!` + CRLF
   - Sayaç şu cevabı verir:
     - `/ZD5ME666-1003` + CRLF

2. **Baudrate seçimi (ACK050)**:
   - Client:
     - `ACK050` + CRLF
   - TCP kullandığımız için baudrate fiziksel olarak değişmez ama **protokol gereği kabul edilir**.
   - Aynı anda sayaç **short/default readout** paketini gönderir:

```text
0.0.0(12345678)
1.8.0(0012345.67*kWh)
2.8.0(0000123.45*kWh)
1.7.0(0001.42*kW)
32.7.0(230.4*V)
0.9.1(HH:MM:SS)
0.9.2(YY-MM-DD)
!
```

3. **Load profile sorgusu (P.01)**:
   - Client, başlangıç ve bitiş tarihini şöyle gönderir:

```text
P.01(YYMMDDhhmm)(YYMMDDhhmm)
Ör: P.01(2401010000)(2401012359)
```

   - Sayaç, istenen aralıktaki tüm kayıtları şu formatta döner:

```text
P.01(2401010000)(0000.42)
P.01(2401010015)(0000.38)
...
!
```

Bu yapı sayesinde:

- **Toplam tüketim (1.8.0)** ≈ **Günlük/haftalık yük profilinin toplamı** olacak şekilde tutarlı bir simülasyon sağlanır.

### 3️⃣ TCP Sunucu

`tcp_server.py` içindeki `MeterTCPServer`:

- Sayaç cihazı gibi davranıp **bağlantıyı kendisi açar**:
  - `bind(host, port)` + `listen()`
- Her yeni client için ayrı bir thread oluşturur.
- Gelen baytları ASCII’ye çevirir, **satır bazında** `ConnectionState`’e iletir:
  - Satır ayracı olarak **CRLF** (veya sadece LF) kabul edilir.
- `ConnectionState.handle_line()` bir cevap üretirse (string), bunu client’a geri yollar.

---

## Örnek Terminal Oturumu

Simülatör arka planda şu şekilde çalışıyor olsun:

```bash
python run_simulator.py --host 127.0.0.1 --port 5000 --interval-seconds 10
```

Başka bir terminalden basit bir TCP client (örneğin `telnet`) ile bağlanabilirsiniz:

```bash
telnet 127.0.0.1 5000
```

1. **Handshake**:

```text
Client:  /?!
Meter :  /ISK5ME382-1003
```

2. **ACK + Short Readout**:

```text
Client:  ACK050
Meter :
 0.0.0(12345678)
 1.8.0(0000005.23*kWh)
 2.8.0(0000000.00*kWh)
 1.7.0(0001.42*kW)
 32.7.0(230.4*V)
 0.9.1(14:22:31)
 0.9.2(24-01-01)
 !
```

3. **Load Profile Sorgusu** (örnek tarih aralığı):

```text
Client:  P.01(2401010000)(2401012359)
Meter :
 P.01(2401010000)(0000.42)
 P.01(2401010015)(0000.38)
 ...
 !
```

> Not: Gerçek çıktılar, simülasyon süresine ve rastgele üretilen tüketime göre değişecektir.

---
## 🔗 Client + Server Etkileşimi
<img width="325" height="550" alt="image" src="https://github.com/user-attachments/assets/1bffdaa9-d343-4b75-95c4-25080fb55ed4" />

<img width="315" height="478" alt="image" src="https://github.com/user-attachments/assets/4aa3a94b-c415-4fce-b25d-abe4391a66ac" />


## Text Bazlı Basit Günlük Tüketim Grafiği

Aşağıdaki, 15 dk aralıklarla yaklaşık **12.34 kWh** toplam tüketime sahip örnek bir günün text tabanlı grafiğidir:

```text
Saat   Tüketim (kWh)   Grafik
-----  --------------  ----------------------------
00:00      0.42        ################
00:15      0.38        ###############
00:30      0.35        #############
00:45      0.40        ###############
01:00      0.50        ####################
...
23:45      0.41        ###############

Toplam ≈ 12.34 kWh  (OBIS 1.8.0 ≈ 12.34 kWh)
```

Bu fikir, ileride eklenecek bir **GUI / web arayüzünde** günlük/haftalık grafikler çizmek için temel oluşturur.

---

## 💡Genişletme Fikirleri

- **Yeni OBIS kodları** (ör: akım, güç faktörü, faz bazlı ölçümler)
- **Seçilebilir profil setleri**:
  - Ev tipi tüketici
  - Sanayi aboneliği
  - Güneş paneli ile üretim senaryosu (2.8.0 kullanılarak)
- **Gerçek TCP/seri köprü**:
  - TCP → Seri port → Gerçek sayaç yönünde proxy
- **UI entegrasyonu**:
  - Tkinter / PyQt / web tabanlı dashboard ile:
    - Anlık güç, gerilim, toplam tüketim,
    - Yük profili grafikleri,
    - Basit alarm/limit uyarıları.

---

## Katkı ve Lisans

Bu repo, test ve eğitim amaçlı bir simülatördür.  
Pull request, yeni OBIS desteği ve iyileştirme önerilerine açıktır.

