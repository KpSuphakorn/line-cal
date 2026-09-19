"""LINE Flex Message template generators for food scans, workouts, snacks, and dashboard."""
from typing import Dict, Any, List
from app.data.presets import WORKOUT_SPLITS, CARDIO_PRESETS, QUICK_SNACKS


def create_food_analyzed_card(food_data: Dict[str, Any], temp_log_id: str) -> Dict[str, Any]:
    """Generate Flex Message card displaying AI food recognition result."""
    calories = food_data.get("calories", 0.0)
    protein = food_data.get("protein", 0.0)
    carbs = food_data.get("carbs", 0.0)
    fat = food_data.get("fat", 0.0)
    food_name = food_data.get("food_name", "อาหารที่ตรวจพบ")
    portion = food_data.get("portion", "1 จาน")
    notes = food_data.get("notes", "บันทึกข้อมูลเรียบร้อย")

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#10B981",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": "🥗 AI Calorie Scanner",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": food_name,
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "xl",
                    "wrap": True,
                    "margin": "sm"
                },
                {
                    "type": "text",
                    "text": f"ปริมาณ: {portion}",
                    "color": "#E6FFFA",
                    "size": "xs",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                # Calories Highlight
                {
                    "type": "box",
                    "layout": "horizontal",
                    "backgroundColor": "#FEF3C7",
                    "cornerRadius": "12px",
                    "paddingAll": "12px",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🔥 พลังงานโดยประมาณ",
                            "size": "sm",
                            "color": "#92400E",
                            "weight": "bold",
                            "flex": 4
                        },
                        {
                            "type": "text",
                            "text": f"{int(calories)} kcal",
                            "size": "xl",
                            "color": "#B45309",
                            "weight": "bold",
                            "align": "end",
                            "flex": 3
                        }
                    ]
                },
                # Macros Breakdown
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "margin": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#EFF6FF",
                            "cornerRadius": "8px",
                            "paddingAll": "8px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🥩 โปรตีน", "size": "xxs", "color": "#1E40AF"},
                                {"type": "text", "text": f"{protein}g", "size": "sm", "weight": "bold", "color": "#1D4ED8"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#F0FDF4",
                            "cornerRadius": "8px",
                            "paddingAll": "8px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🍚 คาร์บ", "size": "xxs", "color": "#166534"},
                                {"type": "text", "text": f"{carbs}g", "size": "sm", "weight": "bold", "color": "#15803D"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#FFF7ED",
                            "cornerRadius": "8px",
                            "paddingAll": "8px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🥑 ไขมัน", "size": "xxs", "color": "#9A3412"},
                                {"type": "text", "text": f"{fat}g", "size": "sm", "weight": "bold", "color": "#C2410C"}
                            ]
                        }
                    ]
                },
                # AI Coach Notes
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F9FAFB",
                    "cornerRadius": "8px",
                    "paddingAll": "10px",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"💡 คำแนะนำ: {notes}",
                            "size": "xs",
                            "color": "#4B5563",
                            "wrap": True
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#10B981",
                    "action": {
                        "type": "postback",
                        "label": "✅ ยืนยันบันทึก",
                        "data": f"action=confirm_food&temp_id={temp_log_id}"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "action": {
                        "type": "postback",
                        "label": "❌ ยกเลิก",
                        "data": "action=cancel"
                    }
                }
            ]
        }
    }


def create_daily_dashboard_card(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Generate modern Daily Summary Card with Progress Bar and Balance."""
    target_kcal = int(summary["target_kcal"])
    eaten_kcal = int(summary["calories_in"])
    burned_kcal = int(summary["calories_burned"])
    remaining = int(summary["remaining_kcal"])
    pct = min(summary["pct_consumed"], 100.0)

    # Status color
    rem_color = "#10B981" if remaining >= 0 else "#EF4444"
    status_text = f"เหลือโควตา {remaining} kcal" if remaining >= 0 else f"เกินเป้าหมาย {abs(remaining)} kcal"

    # Meal history list items
    food_items = []
    for f in summary["food_logs"][:4]:
        food_items.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": f"• {f['time']} {f['name']}", "size": "xs", "color": "#374151", "flex": 5},
                {"type": "text", "text": f"{int(f['calories'])} kcal", "size": "xs", "color": "#6B7280", "align": "end", "flex": 2}
            ]
        })

    if not food_items:
        food_items.append({
            "type": "text",
            "text": "ยังไม่ได้บันทึกอาหารวันนี้",
            "size": "xs",
            "color": "#9CA3AF"
        })

    # Workout history list items
    workout_items = []
    for w in summary["workout_logs"][:3]:
        workout_items.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": f"🏋️ {w['name']}", "size": "xs", "color": "#1E40AF", "flex": 5},
                {"type": "text", "text": f"-{int(w['burned'])} kcal", "size": "xs", "color": "#1D4ED8", "align": "end", "flex": 2}
            ]
        })

    if not workout_items:
        workout_items.append({
            "type": "text",
            "text": "ยังไม่มีบันทึกออกกำลังกายวันนี้",
            "size": "xs",
            "color": "#9CA3AF"
        })

    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0F172A",
            "paddingAll": "18px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "📊 DAILY CALORIE BALANCE", "size": "xs", "color": "#94A3B8", "weight": "bold", "flex": 3},
                        {"type": "text", "text": summary["date_display"], "size": "xs", "color": "#38BDF8", "align": "end", "flex": 2}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": status_text,
                            "size": "xl",
                            "weight": "bold",
                            "color": rem_color,
                            "flex": 4
                        },
                        {
                            "type": "text",
                            "text": f"{pct}%",
                            "size": "md",
                            "weight": "bold",
                            "color": "#E2E8F0",
                            "align": "end",
                            "flex": 1
                        }
                    ]
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                # 3 Stat Cards
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#F1F5F9",
                            "cornerRadius": "8px",
                            "paddingAll": "10px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🎯 เป้าหมาย", "size": "xxs", "color": "#64748B"},
                                {"type": "text", "text": f"{target_kcal}", "size": "md", "weight": "bold", "color": "#0F172A"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#FEF2F2",
                            "cornerRadius": "8px",
                            "paddingAll": "10px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🍽️ กินไปแล้ว", "size": "xxs", "color": "#991B1B"},
                                {"type": "text", "text": f"{eaten_kcal}", "size": "md", "weight": "bold", "color": "#DC2626"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#F0FDF4",
                            "cornerRadius": "8px",
                            "paddingAll": "10px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🔥 เบิร์นออก", "size": "xxs", "color": "#166534"},
                                {"type": "text", "text": f"+{burned_kcal}", "size": "md", "weight": "bold", "color": "#16A34A"}
                            ]
                        }
                    ]
                },
                # Macronutrients Bar
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F8FAFC",
                    "cornerRadius": "8px",
                    "paddingAll": "10px",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🥩 สารอาหารสะสมวันนี้ (Recomposition)",
                            "size": "xs",
                            "weight": "bold",
                            "color": "#334155",
                            "margin": "xs"
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "margin": "sm",
                            "contents": [
                                {"type": "text", "text": f"• โปรตีน: {int(summary['protein'])} / {int(summary['target_protein'])} g", "size": "xs", "color": "#2563EB", "flex": 1},
                                {"type": "text", "text": f"• คาร์บ: {int(summary['carbs'])} / {int(summary['target_carbs'])} g", "size": "xs", "color": "#16A34A", "flex": 1},
                                {"type": "text", "text": f"• ไขมัน: {int(summary['fat'])} / {int(summary['target_fat'])} g", "size": "xs", "color": "#EA580C", "flex": 1}
                            ]
                        }
                    ]
                },
                # Timeline Log of Meals
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "🍴 มื้ออาหารวันนี้:", "size": "xs", "weight": "bold", "color": "#475569"},
                        *food_items
                    ]
                },
                # Timeline Log of Workouts
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "⚡ กิจกรรมออกกำลังกายวันนี้:", "size": "xs", "weight": "bold", "color": "#475569"},
                        *workout_items
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": "🏋️ ตารางเวท 4 วัน",
                                "data": "action=view_workouts"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": "⚡ Quick Snacks",
                                "data": "action=view_snacks"
                            }
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": "📈 สถิติ 7 วัน",
                                "data": "action=view_weekly_stats"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": "🍴 ประวัติอาหาร",
                                "data": "action=view_history"
                            }
                        }
                    ]
                }
            ]
        }
    }


def create_workout_splits_carousel(splits_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate Carousel of Suphakorn's 4-Day Workout Split + Incline Walk."""
    bubbles = []
    source_splits = splits_data if splits_data else WORKOUT_SPLITS

    for split_id, split in source_splits.items():
        exercise_lines = []
        for ex in split["exercises"]:
            exercise_lines.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {"type": "text", "text": f"• {ex['name']}", "size": "xs", "color": "#334155", "flex": 4},
                    {"type": "text", "text": ex["weight"], "size": "xs", "color": "#2563EB", "weight": "bold", "align": "end", "flex": 2}
                ]
            })

        bubbles.append({
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": "#1E293B",
                "paddingAll": "14px",
                "contents": [
                    {"type": "text", "text": split["name"], "color": "#38BDF8", "weight": "bold", "size": "sm", "wrap": True},
                    {"type": "text", "text": f"🔥 เผาผลาญ ~{split['estimated_burn_kcal']} kcal (60 นาที)", "color": "#94A3B8", "size": "xxs", "margin": "xs"}
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "14px",
                "spacing": "xs",
                "contents": exercise_lines
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "paddingAll": "10px",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#2563EB",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": f"✅ จบ {split['name'].split(':')[0]}",
                            "data": f"action=log_workout&split_id={split_id}"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "✏️ แก้ไขน้ำหนักที่เล่น",
                            "data": f"action=edit_split_prompt&split_id={split_id}"
                        }
                    }
                ]
            }
        })

    # Add Cardio Card to Carousel
    bubbles.append({
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#047857",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "🏃 Cardio: เดินชัน (Incline Walk)", "color": "#FFFFFF", "weight": "bold", "size": "sm"},
                {"type": "text", "text": "ความชัน 10-12% | ความเร็ว 4.5-5.0 km/h", "color": "#A7F3D0", "size": "xxs", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "เดินชัน 40 นาที (~280 kcal)",
                        "data": "action=log_cardio&duration=40&burn=280"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "เดินชัน 50 นาที (~350 kcal)",
                        "data": "action=log_cardio&duration=50&burn=350"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "เดินชัน 60 นาที (~420 kcal)",
                        "data": "action=log_cardio&duration=60&burn=420"
                    }
                }
            ]
        }
    })

    return {
        "type": "carousel",
        "contents": bubbles
    }


def create_quick_snacks_card() -> Dict[str, Any]:
    """Generate quick-add menu for Suphakorn's specific snacks and drinks."""
    items = []
    for snack in QUICK_SNACKS:
        items.append({
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#F8FAFC",
            "cornerRadius": "8px",
            "paddingAll": "8px",
            "alignItems": "center",
            "contents": [
                {
                    "type": "text",
                    "text": snack["icon"],
                    "size": "xl",
                    "flex": 1
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "flex": 5,
                    "contents": [
                        {"type": "text", "text": snack["title"], "size": "xs", "weight": "bold", "color": "#1E293B"},
                        {"type": "text", "text": f"{snack['calories']} kcal | P {snack['protein']}g C {snack['carbs']}g F {snack['fat']}g", "size": "xxs", "color": "#64748B"}
                    ]
                },
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#10B981",
                    "height": "sm",
                    "flex": 2,
                    "action": {
                        "type": "postback",
                        "label": "+บันทึก",
                        "data": f"action=quick_snack&snack_id={snack['id']}"
                    }
                }
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#059669",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "⚡ Quick Log ของว่าง & มัจฉะ", "color": "#FFFFFF", "weight": "bold", "size": "md"},
                {"type": "text", "text": "แตะครั้งเดียวบันทึกทันทีตรงเข้ายอดประจำวัน", "color": "#D1FAE5", "size": "xxs", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "spacing": "sm",
            "contents": items
        }
    }


def create_workout_logged_card(title: str, burned_kcal: float, remaining_kcal: float) -> Dict[str, Any]:
    """Generate Card notifying workout completion and updated calorie quota."""
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E3A8A",
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": "🔥 บันทึกการออกกำลังกายแล้ว!", "color": "#60A5FA", "size": "xs", "weight": "bold"},
                {"type": "text", "text": title, "color": "#FFFFFF", "size": "lg", "weight": "bold", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "sm",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "พลังงานที่เผาผลาญ:", "size": "sm", "color": "#475569", "flex": 4},
                        {"type": "text", "text": f"+{int(burned_kcal)} kcal", "size": "sm", "weight": "bold", "color": "#16A34A", "align": "end", "flex": 3}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "โควตาแคลอรีที่กินได้เพิ่ม:", "size": "sm", "color": "#475569", "flex": 4},
                        {"type": "text", "text": f"{int(remaining_kcal)} kcal", "size": "sm", "weight": "bold", "color": "#2563EB", "align": "end", "flex": 3}
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "📊 ดูสรุปยอดวันนี้",
                        "data": "action=view_dashboard"
                    }
                }
            ]
        }
    }


def create_weekly_stats_card(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Generate 7-day Weekly Fitness & Nutrition Performance Card."""
    split = stats["split_done"]
    d1_icon = "✅" if split["day_1"] else "⏳"
    d2_icon = "✅" if split["day_2"] else "⏳"
    d3_icon = "✅" if split["day_3"] else "⏳"
    d4_icon = "✅" if split["day_4"] else "⏳"

    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#312E81",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "📈 WEEKLY FITNESS STATS", "size": "xs", "color": "#A5B4FC", "weight": "bold", "flex": 3},
                        {"type": "text", "text": f"{stats['start_date']} - {stats['end_date']}", "size": "xs", "color": "#C7D2FE", "align": "end", "flex": 2}
                    ]
                },
                {
                    "type": "text",
                    "text": "ภาพรวมสถิติและความสม่ำเสมอ 7 วัน",
                    "size": "md",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "md",
            "contents": [
                # 2 Stat Cards: Avg Calories & Avg Protein
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#EEF2FF",
                            "cornerRadius": "8px",
                            "paddingAll": "10px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🔥 แคลอรีเฉลี่ย/วัน", "size": "xxs", "color": "#4338CA"},
                                {"type": "text", "text": f"{int(stats['avg_daily_calories'])}", "size": "lg", "weight": "bold", "color": "#3730A3"},
                                {"type": "text", "text": f"เป้า: {int(stats['target_kcal'])} kcal", "size": "xxs", "color": "#6366F1"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#EFF6FF",
                            "cornerRadius": "8px",
                            "paddingAll": "10px",
                            "flex": 1,
                            "alignItems": "center",
                            "contents": [
                                {"type": "text", "text": "🥩 โปรตีนเฉลี่ย/วัน", "size": "xxs", "color": "#1E40AF"},
                                {"type": "text", "text": f"{int(stats['avg_daily_protein'])}g", "size": "lg", "weight": "bold", "color": "#1D4ED8"},
                                {"type": "text", "text": f"เป้า: {int(stats['target_protein'])}g", "size": "xxs", "color": "#3B82F6"}
                            ]
                        }
                    ]
                },
                # 4-Day Workout Split Checklist
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F8FAFC",
                    "cornerRadius": "8px",
                    "paddingAll": "10px",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "🏋️‍♂️ ตารางเวท 4 วันประจำสัปดาห์", "size": "xs", "weight": "bold", "color": "#1E293B", "flex": 4},
                                {"type": "text", "text": f"{stats['weights_completed']}/{stats['weights_target']} วัน", "size": "xs", "weight": "bold", "color": "#2563EB", "align": "end", "flex": 1}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "margin": "sm",
                            "spacing": "xs",
                            "contents": [
                                {
                                    "type": "box",
                                    "layout": "horizontal",
                                    "contents": [
                                        {"type": "text", "text": f"{d1_icon} Day 1: Push (อก/ไหล่/หลังแขน)", "size": "xs", "color": "#334155"}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "horizontal",
                                    "contents": [
                                        {"type": "text", "text": f"{d2_icon} Day 2: Pull (หลัง/ไหล่หลัง/หน้าแขน)", "size": "xs", "color": "#334155"}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "horizontal",
                                    "contents": [
                                        {"type": "text", "text": f"{d3_icon} Day 3: Lower & Core (ขา 4 ท่า + ท้อง)", "size": "xs", "color": "#334155"}
                                    ]
                                },
                                {
                                    "type": "box",
                                    "layout": "horizontal",
                                    "contents": [
                                        {"type": "text", "text": f"{d4_icon} Day 4: Upper (ท่อนบนรวม)", "size": "xs", "color": "#334155"}
                                    ]
                                }
                            ]
                        }
                    ]
                },
                # Cardio Incline Walk Tracker
                {
                    "type": "box",
                    "layout": "horizontal",
                    "backgroundColor": "#F0FDF4",
                    "cornerRadius": "8px",
                    "paddingAll": "10px",
                    "alignItems": "center",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"🏃 เดินชัน (เป้า 2 วัน/wk):",
                            "size": "xs",
                            "weight": "bold",
                            "color": "#166534",
                            "flex": 4
                        },
                        {
                            "type": "text",
                            "text": f"{stats['cardio_count']}/2 ครั้ง ({stats['cardio_minutes']} นาที)",
                            "size": "xs",
                            "weight": "bold",
                            "color": "#15803D",
                            "align": "end",
                            "flex": 3
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "📊 ดูยอดวันนี้",
                        "data": "action=view_dashboard"
                    }
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "🍴 ประวัติอาหาร",
                        "data": "action=view_history"
                    }
                }
            ]
        }
    }


def create_food_history_card(history_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate Recent Meals History Card."""
    rows = []
    for item in history_items[:8]:
        rows.append({
            "type": "box",
            "layout": "horizontal",
            "paddingAll": "6px",
            "contents": [
                {"type": "text", "text": f"{item['date']} {item['time']}", "size": "xxs", "color": "#64748B", "flex": 2},
                {"type": "text", "text": item["name"], "size": "xs", "weight": "bold", "color": "#1E293B", "flex": 5},
                {"type": "text", "text": f"{item['calories']} kcal", "size": "xs", "weight": "bold", "color": "#EA580C", "align": "end", "flex": 2}
            ]
        })

    if not rows:
        rows.append({
            "type": "text",
            "text": "ยังไม่มีประวัติอาหารในระบบ",
            "size": "xs",
            "color": "#94A3B8"
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#D97706",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "🍴 ประวัติรายการอาหารล่าสุด", "color": "#FFFFFF", "weight": "bold", "size": "md"},
                {"type": "text", "text": "รายการอาหารที่บันทึกไว้ในฐานข้อมูล", "color": "#FEF3C7", "size": "xxs", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "spacing": "xs",
            "contents": rows
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "📊 ดูสรุปยอดวันนี้",
                        "data": "action=view_dashboard"
                    }
                }
            ]
        }
    }


def create_main_hub_card() -> Dict[str, Any]:
    """Generate the Visual Main Hub / Menu Card for all bot features."""
    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#0F172A",
            "paddingAll": "18px",
            "contents": [
                {
                    "type": "text",
                    "text": "🌟 CALORIE & FITNESS COMPANION",
                    "size": "xs",
                    "weight": "bold",
                    "color": "#38BDF8"
                },
                {
                    "type": "text",
                    "text": "ศูนย์รวมคำสั่งใช้งาน (Main Menu)",
                    "size": "lg",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "margin": "xs"
                },
                {
                    "type": "text",
                    "text": "แตะเลือกฟังก์ชันที่ต้องการได้ทันที ไม่ต้องจำคำสั่งพิมพ์ครับ",
                    "size": "xxs",
                    "color": "#94A3B8",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "sm",
            "contents": [
                # Row 1: Camera & Dashboard
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#ECFDF5",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "uri",
                                "label": "ถ่ายรูปอาหาร",
                                "uri": "https://line.me/R/nv/camera/"
                            },
                            "contents": [
                                {"type": "text", "text": "📸 ถ่ายรูปอาหาร", "size": "sm", "weight": "bold", "color": "#065F46"},
                                {"type": "text", "text": "เปิดกล้องสแกนแคล", "size": "xxs", "color": "#047857", "margin": "xs"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#EFF6FF",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "postback",
                                "label": "สรุปยอดวันนี้",
                                "data": "action=view_dashboard"
                            },
                            "contents": [
                                {"type": "text", "text": "📊 สรุปยอดวันนี้", "size": "sm", "weight": "bold", "color": "#1E40AF"},
                                {"type": "text", "text": "ดูโควตา & Balance", "size": "xxs", "color": "#2563EB", "margin": "xs"}
                            ]
                        }
                    ]
                },
                # Row 2: Workout 4-Day & Incline Walk
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#F5F3FF",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "postback",
                                "label": "ตารางเวท 4 วัน",
                                "data": "action=view_workouts"
                            },
                            "contents": [
                                {"type": "text", "text": "🏋️‍♂️ ตารางเวท 4 วัน", "size": "sm", "weight": "bold", "color": "#5B21B6"},
                                {"type": "text", "text": "Push/Pull/Lower/Upper", "size": "xxs", "color": "#6D28D9", "margin": "xs"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#F0FDF4",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "postback",
                                "label": "เดินชัน",
                                "data": "action=view_workouts"
                            },
                            "contents": [
                                {"type": "text", "text": "🏃 เดินชัน Cardio", "size": "sm", "weight": "bold", "color": "#166534"},
                                {"type": "text", "text": "40 / 50 / 60 นาที", "size": "xxs", "color": "#15803D", "margin": "xs"}
                            ]
                        }
                    ]
                },
                # Row 3: Quick Snacks & Weekly Stats
                {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#FEF3C7",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "postback",
                                "label": "Quick Snacks",
                                "data": "action=view_snacks"
                            },
                            "contents": [
                                {"type": "text", "text": "⚡ Quick Snacks", "size": "sm", "weight": "bold", "color": "#92400E"},
                                {"type": "text", "text": "กล้วย นม มัจฉะ ถั่ว", "size": "xxs", "color": "#B45309", "margin": "xs"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": "#FDF2F8",
                            "cornerRadius": "10px",
                            "paddingAll": "12px",
                            "flex": 1,
                            "action": {
                                "type": "postback",
                                "label": "สถิติ 7 วัน",
                                "data": "action=view_weekly_stats"
                            },
                            "contents": [
                                {"type": "text", "text": "📈 สถิติ 7 วัน", "size": "sm", "weight": "bold", "color": "#9D174D"},
                                {"type": "text", "text": "เฉลี่ยแคล & โปรตีน", "size": "xxs", "color": "#BE185D", "margin": "xs"}
                            ]
                        }
                    ]
                },
                # Row 4: Edit Routine & Weights Button
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#F1F5F9",
                    "cornerRadius": "10px",
                    "paddingAll": "12px",
                    "action": {
                        "type": "postback",
                        "label": "แก้ไขน้ำหนักเวท",
                        "data": "action=view_edit_menu"
                    },
                    "contents": [
                        {"type": "text", "text": "✏️ ปรับแก้ตารางและน้ำหนักที่เล่น (Edit Weights)", "size": "xs", "weight": "bold", "color": "#334155", "align": "center"}
                    ]
                }
            ]
        }
    }


def create_edit_split_prompt_card(split: Dict[str, Any]) -> Dict[str, Any]:
    """Generate prompt card showing exercises and how to update weight."""
    exercise_lines = []
    for ex in split["exercises"]:
        exercise_lines.append({
            "type": "box",
            "layout": "horizontal",
            "paddingAll": "4px",
            "contents": [
                {"type": "text", "text": f"• {ex['name']}", "size": "xs", "color": "#1E293B", "flex": 4},
                {"type": "text", "text": ex["weight"], "size": "xs", "weight": "bold", "color": "#2563EB", "align": "end", "flex": 2}
            ]
        })

    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1E293B",
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": "✏️ แก้ไขน้ำหนักเวท", "color": "#38BDF8", "size": "xs", "weight": "bold"},
                {"type": "text", "text": split["name"], "color": "#FFFFFF", "size": "md", "weight": "bold", "margin": "xs"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "spacing": "xs",
            "contents": [
                {"type": "text", "text": "รายการท่าและน้ำหนักปัจจุบัน:", "size": "xs", "weight": "bold", "color": "#64748B"},
                *exercise_lines,
                {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#FEF3C7",
                    "cornerRadius": "8px",
                    "paddingAll": "10px",
                    "margin": "md",
                    "contents": [
                        {"type": "text", "text": "💡 วิธีเปลี่ยนน้ำหนัก:", "size": "xs", "weight": "bold", "color": "#92400E"},
                        {"type": "text", "text": "พิมพ์: แก้น้ำหนัก [ชื่อท่า] [น้ำหนัก]\nเช่น:\n• แก้น้ำหนัก pec dec fly 45\n• แก้น้ำหนัก bench press 25\n• แก้น้ำหนัก lat pull down 40", "size": "xxs", "color": "#78350F", "wrap": True, "margin": "xs"}
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "🏋️ กลับไปดูตารางเวท",
                        "data": "action=view_workouts"
                    }
                }
            ]
        }
    }


def create_weight_updated_card(exercise_name: str, new_weight: str) -> Dict[str, Any]:
    """Generate confirmation card after weight is updated."""
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#059669",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "✅ อัปเดตน้ำหนักสำเร็จ!", "color": "#FFFFFF", "size": "sm", "weight": "bold"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": f"ท่า: {exercise_name}", "size": "sm", "weight": "bold", "color": "#1E293B"},
                {"type": "text", "text": f"น้ำหนักใหม่: {new_weight}", "size": "md", "weight": "bold", "color": "#2563EB", "margin": "xs"},
                {"type": "text", "text": "บันทึกลงในฐานข้อมูลเรียบร้อย", "size": "xxs", "color": "#64748B", "margin": "xs"}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "10px",
            "contents": [
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "postback",
                        "label": "🏋️ ดูตารางเวทที่อัปเดตแล้ว",
                        "data": "action=view_workouts"
                    }
                }
            ]
        }
    }
