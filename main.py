import os
import sys
import yaml
import asyncio
import argparse
import logging
from datetime import datetime
from xiaomi_s400_live import S400Scale
from src.storage import StorageManager
from src.user_manager import UserManager
from src.notifier import send_windows_notification

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("S400Recorder")

def load_config(config_path: str = "config.yaml") -> dict:
    if not os.path.exists(config_path):
        print(f"[錯誤] 找不到設定檔：{config_path}")
        print("請確保已建立 config.yaml 並設定好 MAC 與 Bindkey。")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def print_banner():
    banner = r"""
============================================================
      Xiaomi 體脂計 S400 (MJTZC01YM) 數據記錄服務 (Win11)
============================================================
    """
    print(banner)

def print_measurement_result(user_name: str, metrics: dict, weight: float, imp_high: float, imp_low: float):
    print("\n" + "="*60)
    print(f"  測量完成！ 使用者: {user_name}  |  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    print(f"  體重 (Weight)        : {weight:.2f} kg")
    if metrics:
        bmi_st = f" ({metrics.get('bmi_status')})" if metrics.get('bmi_status') else ""
        fat_st = f" ({metrics.get('fat_status')})" if metrics.get('fat_status') else ""
        vis_st = f" ({metrics.get('visceral_status')})" if metrics.get('visceral_status') else ""
        water_st = f" ({metrics.get('water_status')})" if metrics.get('water_status') else ""

        print(f"  身體質量指數 (BMI)   : {metrics.get('bmi', 'N/A')}{bmi_st}")
        print(f"  體脂率 (Body Fat)    : {metrics.get('fat_percent', 'N/A')} %{fat_st}")
        print(f"  肌肉量 (Muscle Mass) : {metrics.get('muscle_mass_kg', 'N/A')} kg")
        print(f"  水分率 (Water)       : {metrics.get('water_percent', 'N/A')} %{water_st}")
        print(f"  內臟脂肪 (Visceral)  : {metrics.get('visceral_fat', 'N/A')}{vis_st}")
        print(f"  基礎代謝 (BMR)       : {metrics.get('bmr_kcal_day', 'N/A')} kcal")
        print(f"  骨量 (Bone Mass)     : {metrics.get('bone_mass_kg', 'N/A')} kg")
        print(f"  蛋白質率 (Protein)   : {metrics.get('protein_percent', 'N/A')} %")
        print(f"  代謝年齡 (Meta Age)  : {metrics.get('metabolic_age_years', 'N/A')} 歲")
        print(f"  身體類型 (Body Type) : {metrics.get('body_type_name', 'N/A')}")
        print(f"  理想體重 (Ideal Wt)  : {metrics.get('ideal_weight_kg', 'N/A')} kg")
    if imp_high or imp_low:
        print(f"  高頻阻抗 (250kHz)    : {imp_high if imp_high else 'N/A'} Ω")
        print(f"  低頻阻抗 (50kHz)     : {imp_low if imp_low else 'N/A'} Ω")
    print("="*60 + "\n")

async def record_session(mac: str, bindkey_bytes: bytes, token_bytes: bytes, user_mgr: UserManager, storage: StorageManager) -> bool:
    print(f"\n[等待中] 正在搜尋體脂計 {mac} ...")
    print(">> 請脫襪雙腳站上體脂計喚醒藍牙並開始測量 <<\n")

    scale = S400Scale(
        mac=mac,
        bindkey=bindkey_bytes,
        token=token_bytes,
        connect_timeout=35.0
    )

    try:
        async with scale:
            print("[連線成功] 已成功握手連接體脂計 S400！正在等待穩定數值...")
            async for ev in scale.events():
                if ev.type == "live":
                    w = ev.weight_kg if ev.weight_kg is not None else 0.0
                    status = "鎖定中..." if ev.stable else "測量中..."
                    sys.stdout.write(f"\r[即時動態] 目前體重: {w:6.2f} kg  ({status}) ")
                    sys.stdout.flush()

                elif ev.type == "final":
                    sys.stdout.write("\r" + " "*60 + "\r")
                    weight = ev.weight_kg
                    imp_high = ev.impedance_ohm
                    imp_low = ev.impedance_low_ohm

                    if weight is None or weight <= 0:
                        print("[警告] 收到無效測量數據。")
                        continue

                    # 比對使用者
                    matched_user = user_mgr.find_user_by_weight(weight)
                    user_name = matched_user.get("name", "Unknown") if matched_user else "訪客/未登錄"
                    user_id = matched_user.get("id", None) if matched_user else None

                    # 計算體成分 (若有阻抗與使用者資料)
                    metrics = {}
                    imp_val = imp_high or imp_low
                    if matched_user and imp_val and imp_val > 0:
                        try:
                            metrics = user_mgr.calculate_metrics(
                                weight_kg=weight,
                                impedance_high=imp_high,
                                user_dict=matched_user,
                                impedance_low=imp_low
                            )
                        except Exception as e:
                            logger.error(f"計算體組成失敗: {e}")

                    # 終端顯示結果
                    print_measurement_result(user_name, metrics, weight, imp_high, imp_low)

                    # 儲存至資料庫與 CSV
                    record = {
                        "user_id": user_id,
                        "user_name": user_name,
                        "weight_kg": weight,
                        "impedance_ohm": imp_high,
                        "impedance_low_ohm": imp_low,
                        "bmi": metrics.get("bmi"),
                        "fat_percent": metrics.get("fat_percent"),
                        "water_percent": metrics.get("water_percent"),
                        "muscle_mass_kg": metrics.get("muscle_mass_kg"),
                        "bone_mass_kg": metrics.get("bone_mass_kg"),
                        "visceral_fat": metrics.get("visceral_fat"),
                        "bmr_kcal_day": metrics.get("bmr_kcal_day"),
                        "protein_percent": metrics.get("protein_percent"),
                        "metabolic_age_years": metrics.get("metabolic_age_years"),
                        "body_type_name": metrics.get("body_type_name"),
                        "ideal_weight_kg": metrics.get("ideal_weight_kg"),
                        "raw_data": ev.raw_plaintext.hex() if ev.raw_plaintext else ""
                    }
                    rec_id = storage.save_measurement(record)
                    print(f"[儲存成功] 資料已儲存至資料庫 (ID: {rec_id}) 及 CSV 檔案。")

                    # 發送 Windows 通知
                    fat_str = f"，體脂: {metrics.get('fat_percent')}%" if metrics.get('fat_percent') else ""
                    send_windows_notification(
                        title=f"體脂計紀錄成功 ({user_name})",
                        message=f"體重: {weight:.2f} kg{fat_str}"
                    )

                    # 測量完畢，結束當前 session
                    scale.stop()
                    return True

    except TimeoutError:
        print("[逾時] 藍牙連線逾時，請確認體脂計是否已被點亮或人在範圍內。")
        return False
    except Exception as e:
        logger.warning(f"通訊過程發生異常: {e}")
        return False

    return False

def show_history(storage: StorageManager):
    records = storage.get_recent(10)
    if not records:
        print("\n尚無任何測量記錄。\n")
        return
    print("\n" + "="*80)
    print(f"{'時間':<20} {'姓名':<10} {'體重(kg)':<10} {'體脂(%)':<10} {'BMI':<8} {'肌肉量(kg)':<10}")
    print("="*80)
    for r in records:
        ts = r.get("timestamp", "")
        name = r.get("user_name", "") or "Unknown"
        w = f"{r.get('weight_kg', 0):.2f}"
        fat = f"{r.get('fat_percent', 0):.1f}" if r.get('fat_percent') is not None else "-"
        bmi = f"{r.get('bmi', 0):.1f}" if r.get('bmi') is not None else "-"
        m = f"{r.get('muscle_mass_kg', 0):.2f}" if r.get('muscle_mass_kg') is not None else "-"
        print(f"{ts:<20} {name:<10} {w:<10} {fat:<10} {bmi:<8} {m:<10}")
    print("="*80 + "\n")

async def main_async(args):
    config = load_config()
    dev_conf = config.get("device", {})
    mac = dev_conf.get("mac")
    bindkey_hex = dev_conf.get("bindkey")
    token_hex = dev_conf.get("token")

    if not mac or not bindkey_hex:
        print("[錯誤] config.yaml 中的 device.mac 或 device.bindkey 未設定。")
        return

    bindkey_bytes = bytes.fromhex(bindkey_hex)
    token_bytes = bytes.fromhex(token_hex) if token_hex else None

    storage_conf = config.get("storage", {})
    storage = StorageManager(
        db_path=storage_conf.get("database_path", "data/measurements.db"),
        export_csv=storage_conf.get("export_csv", True),
        csv_path=storage_conf.get("csv_path", "data/measurements.csv")
    )
    user_mgr = UserManager(config.get("users", []))

    if args.history:
        show_history(storage)
        return

    print_banner()

    if args.once:
        print("[模式] 單次記錄模式 (量測一次後結束)")
        await record_session(mac, bindkey_bytes, token_bytes, user_mgr, storage)
    else:
        print("[模式] 持續常駐監聽模式 (按 Ctrl+C 可停止)")
        while True:
            try:
                success = await record_session(mac, bindkey_bytes, token_bytes, user_mgr, storage)
                if success:
                    print("\n[待命] 休息 8 秒以避免重複觸發，隨後繼續等待下次測量...")
                    await asyncio.sleep(8)
                else:
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"意外錯誤: {e}")
                await asyncio.sleep(3)

def main():
    parser = argparse.ArgumentParser(description="Xiaomi 體脂計 S400 (Win11) 記錄器")
    parser.add_argument("--once", action="store_true", help="僅記錄一次測量後退出")
    parser.add_argument("--history", action="store_true", help="檢視最近 10 筆歷史記錄")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n\n已手動停止監聽服務。")

if __name__ == "__main__":
    main()
