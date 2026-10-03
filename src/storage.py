import os
import sqlite3
import csv
from datetime import datetime
from typing import Optional, Dict, Any, List

class StorageManager:
    def __init__(self, db_path: str = "data/measurements.db", export_csv: bool = True, csv_path: str = "data/measurements.csv"):
        self.db_path = db_path
        self.export_csv = export_csv
        self.csv_path = csv_path
        
        # 確保目錄存在
        for path in [self.db_path, self.csv_path]:
            dir_name = os.path.dirname(path)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
                
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id INTEGER,
                    user_name TEXT,
                    weight_kg REAL NOT NULL,
                    impedance_ohm REAL,
                    impedance_low_ohm REAL,
                    bmi REAL,
                    fat_percent REAL,
                    water_percent REAL,
                    muscle_mass_kg REAL,
                    bone_mass_kg REAL,
                    visceral_fat REAL,
                    bmr_kcal_day INTEGER,
                    protein_percent REAL,
                    metabolic_age_years INTEGER,
                    body_type_name TEXT,
                    ideal_weight_kg REAL,
                    raw_data TEXT
                )
            """)
            conn.commit()

    def save_measurement(self, record: Dict[str, Any]) -> int:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record_time = record.get("timestamp_str", now_str)

        row = {
            "timestamp": record_time,
            "user_id": record.get("user_id"),
            "user_name": record.get("user_name"),
            "weight_kg": record.get("weight_kg"),
            "impedance_ohm": record.get("impedance_ohm"),
            "impedance_low_ohm": record.get("impedance_low_ohm"),
            "bmi": record.get("bmi"),
            "fat_percent": record.get("fat_percent"),
            "water_percent": record.get("water_percent"),
            "muscle_mass_kg": record.get("muscle_mass_kg"),
            "bone_mass_kg": record.get("bone_mass_kg"),
            "visceral_fat": record.get("visceral_fat"),
            "bmr_kcal_day": record.get("bmr_kcal_day"),
            "protein_percent": record.get("protein_percent"),
            "metabolic_age_years": record.get("metabolic_age_years"),
            "body_type_name": record.get("body_type_name"),
            "ideal_weight_kg": record.get("ideal_weight_kg"),
            "raw_data": str(record.get("raw_data", ""))
        }

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            fields = list(row.keys())
            placeholders = ", ".join(["?"] * len(fields))
            sql = f"INSERT INTO measurements ({', '.join(fields)}) VALUES ({placeholders})"
            cursor.execute(sql, [row[f] for f in fields])
            conn.commit()
            record_id = cursor.lastrowid

        if self.export_csv:
            self._append_csv(row)

        try:
            self.export_data_files()
        except Exception:
            pass

        return record_id

    def _append_csv(self, row: Dict[str, Any]):
        file_exists = os.path.exists(self.csv_path)
        with open(self.csv_path, mode="a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def get_recent(self, limit: int = 25) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM measurements ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_all_measurements(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM measurements ORDER BY timestamp DESC")
            return [dict(r) for r in cursor.fetchall()]

    def export_data_files(self, json_path: str = "data/measurements.json", js_path: str = "data/measurements.js"):
        import json
        records = self.get_all_measurements()
        
        # 1. 輸出 JSON 檔 (供 GitHub Pages / Web API fetch 使用)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
            
        # 2. 輸出 JS 檔 (供本機 Chrome file:/// 直接開啟，避免 CORS 限制)
        with open(js_path, "w", encoding="utf-8") as f:
            f.write(f"window.MEASUREMENTS_DATA = {json.dumps(records, ensure_ascii=False, indent=2)};\n")

    def delete_below_weight(self, min_weight_kg: float = 50.0) -> int:
        """刪除體重低於門檻的誤測紀錄，並同步重寫 CSV 與前端檔案。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM measurements WHERE weight_kg < ?", (min_weight_kg,))
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            records = self.get_all_measurements()
            records_asc = sorted(records, key=lambda x: x["timestamp"])
            if self.export_csv and records_asc:
                fieldnames = list(records_asc[0].keys())
                with open(self.csv_path, mode="w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for r in records_asc:
                        writer.writerow(r)
            self.export_data_files()
        return deleted


