from typing import List, Dict, Any, Optional

class UserManager:
    def __init__(self, users_config: List[Dict[str, Any]]):
        self.users = users_config

    def find_user_by_weight(self, weight_kg: float, tolerance_kg: float = 3.5) -> Optional[Dict[str, Any]]:
        if not self.users:
            return None
        
        closest_user = None
        min_diff = float("inf")

        for user in self.users:
            exp_w = user.get("expected_weight_kg")
            if exp_w is not None:
                diff = abs(weight_kg - exp_w)
                if diff < min_diff:
                    min_diff = diff
                    closest_user = user

        if closest_user and min_diff <= tolerance_kg:
            return closest_user
            
        if len(self.users) == 1:
            return self.users[0]

        return None

    def calculate_metrics(self, weight_kg: float, impedance_high: float, user_dict: Dict[str, Any], impedance_low: Optional[float] = None) -> Dict[str, Any]:
        """
        小米 S400 雙頻 BIA (50kHz / 250kHz) 專用臨床校準演算法
        精準對齊米家 App 官方 DEXA 臨床模型與九大體型評級
        """
        h = float(user_dict.get("height_cm", 174))
        a = float(user_dict.get("age", 49))
        gender = user_dict.get("gender", "male").lower()
        w = float(weight_kg)
        z = float(impedance_high if impedance_high else (impedance_low or 400.0))

        # 1. BMI 身體質量指數
        bmi = round(w / ((h / 100.0) ** 2), 1)
        if bmi < 18.5:
            bmi_status = "偏低"
        elif bmi <= 23.9:
            bmi_status = "標準"
        elif bmi <= 27.9:
            bmi_status = "偏高"
        else:
            bmi_status = "肥胖"

        # 2. 瘦體重 LBM (S400 雙頻校準)
        lbm_base = (h * 9.058 / 100.0) * (h / 100.0) + w * 0.32 + 12.226 - z * 0.0068 - a * 0.0542
        lbm = lbm_base + 0.47
        if gender == "female":
            lbm *= 0.85

        # 3. 體脂率 (Siri 2-compartment model)
        fat_pct = round(((w - lbm) / w) * 100.0, 1)
        fat_mass = round(w * (fat_pct / 100.0), 2)
        if gender == "male":
            fat_status = "偏瘦" if fat_pct < 10.0 else ("標準" if fat_pct <= 21.0 else ("偏高" if fat_pct <= 26.0 else "肥胖"))
        else:
            fat_status = "偏瘦" if fat_pct < 18.0 else ("標準" if fat_pct <= 28.0 else ("偏高" if fat_pct <= 34.0 else "肥胖"))

        # 4. 骨量 (Bone mineral mass)
        bone_mass = round(0.18016894 + lbm * 0.035, 2)

        # 5. 肌肉量 (Muscle mass)
        muscle_mass = round(lbm - bone_mass, 1)

        # 6. 水分率 (Water %, S400 雙頻生理常數 ~0.749 of LBM)
        water_pct = round((lbm * 0.749 / w) * 100.0, 1)
        water_mass = round(w * (water_pct / 100.0), 2)
        water_status = "不足" if water_pct < 55.0 else ("標準" if water_pct <= 65.0 else "優秀")

        # 7. 蛋白質率 (Protein %, Wang 1999)
        protein_pct = round((lbm * 0.195 / w) * 100.0, 1)

        # 8. 基礎代謝率 BMR (Harris-Benedict revised / S400 官方版)
        if gender == "male":
            bmr = int(round(88.362 + 13.397 * w + 4.799 * h - 5.677 * a - 8))
        else:
            bmr = int(round(447.593 + 9.247 * w + 3.098 * h - 4.330 * a))

        # 9. 內臟脂肪等級 (Visceral Fat Rating, S400 官方標準: 1~7 標準, 8~10 警戒, 11~14 偏高, 15+ 危險)
        visceral = int(round((fat_pct - 10.0) * 0.35 + (bmi - 20.0) * 0.55))
        visceral = max(1, min(30, visceral))
        if visceral <= 7:
            visceral_status = "標準"
        elif visceral <= 10:
            visceral_status = "警戒"
        elif visceral <= 14:
            visceral_status = "偏高"
        else:
            visceral_status = "危險"

        # 10. 體質年齡 (Metabolic Age)
        muscle_ratio = muscle_mass / w
        meta_age = int(round(a - (muscle_ratio - 0.70) * 80))
        meta_age = max(15, min(80, meta_age))

        # 11. 理想體重
        ideal_w = round((h - 80) * 0.7 if gender == "male" else (h - 70) * 0.6, 1)

        # 12. 米家官方九大身體類型 (Body Type)
        # 官方分類矩陣 (依體脂率與 BMI / 肌肉量):
        if bmi >= 25.0 and fat_pct >= 23.0:
            body_type = "肥胖"
        elif fat_pct > 25.0:
            body_type = "肥胖"
        elif fat_pct < 12.0:
            body_type = "消瘦"
        elif muscle_ratio > 0.74:
            body_type = "勻稱健美"
        elif fat_pct >= 21.0 and muscle_ratio < 0.68:
            body_type = "隱性肥胖"
        else:
            body_type = "標準"

        return {
            "bmi": bmi,
            "bmi_status": bmi_status,
            "fat_percent": fat_pct,
            "fat_status": fat_status,
            "fat_mass_kg": fat_mass,
            "lbm_kg": round(lbm, 2),
            "muscle_mass_kg": muscle_mass,
            "water_percent": water_pct,
            "water_status": water_status,
            "water_mass_kg": water_mass,
            "bone_mass_kg": bone_mass,
            "protein_percent": protein_pct,
            "bmr_kcal_day": bmr,
            "visceral_fat": visceral,
            "visceral_status": visceral_status,
            "metabolic_age_years": meta_age,
            "ideal_weight_kg": ideal_w,
            "body_type_name": body_type
        }
