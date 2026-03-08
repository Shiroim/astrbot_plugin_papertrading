import json
import os
import shutil
import time
from pathlib import Path

# ================= 配置 =================
# 数据目录路径 (请根据实际情况修改)
# 通常在 AstrBot/data/plugins/papertrading
# 数据目录路径 (请根据实际情况修改)

DATA_DIR = "../../../plugin_data/papertrading" 

def backup_data(data_path: Path):
    """备份数据"""
    backup_path = data_path / f"backup_{int(time.time())}"
    if not backup_path.exists():
        backup_path.mkdir()
        
    for filename in ['users.json', 'positions.json', 'orders.json']:
        src = data_path / filename
        if src.exists():
            shutil.copy2(src, backup_path / filename)
    
    print(f"✅ 数据已备份至: {backup_path}")

def fix_user_ids():
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        print(f"❌ 找不到数据目录: {data_path}")
        print("请修改脚本中的 DATA_DIR 变量为正确的路径")
        return

    print(f"📂 开始扫描数据目录: {data_path}")
    backup_data(data_path)
    
    # 1. 扫描需要修复的用户ID
    id_map = {} # old_long_id -> new_short_id
    
    try:
        with open(data_path / 'users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        print(f"用户总数: {len(users)}")
        
        for user_id in list(users.keys()):
            # user_id 格式: platform:sender_id:session_id
            parts = user_id.split(':')
            if len(parts) >= 3:
                platform = parts[0]
                sender_id = parts[1]
                session_id = parts[2]
                
                # 检查 session_id 是否包含 sender_id 前缀 (例如 123456_987654)
                if "_" in session_id:
                    if session_id.startswith(f"{sender_id}_"):
                        # 发现问题ID
                        real_user_qq = session_id[len(sender_id)+1:]
                        new_short_id = f"{platform}:{sender_id}:{real_user_qq}"
                        
                        print(f"🔍 发现待修复ID: {user_id} -> {new_short_id}")
                        id_map[user_id] = new_short_id
        
        if not id_map:
            print("✅ 未发现需要修复的用户ID")
            return

        print(f"📋 共发现 {len(id_map)} 个需要迁移的用户")
        
        # 2. 修复 users.json
        new_users = users.copy()
        for old_id, new_id in id_map.items():
            user_data = new_users.pop(old_id)
            user_data['user_id'] = new_id # 更新内部字段
            
            if new_id in new_users:
                print(f"⚠️ 冲突: 用户 {new_id} 已存在!")
                print(f"   保留旧数据 (资产: {new_users[new_id].get('total_assets')})")
                print(f"   丢弃新数据 (资产: {user_data.get('total_assets')})")
                # 可以在这里实现合并逻辑，目前策略是保留已存在的短ID账号 (通常是更早注册的)
            else:
                new_users[new_id] = user_data
                print(f"✨ 迁移用户数据: {old_id} -> {new_id}")
        
        with open(data_path / 'users.json', 'w', encoding='utf-8') as f:
            json.dump(new_users, f, ensure_ascii=False, indent=2)
            
        # 3. 修复 positions.json
        if (data_path / 'positions.json').exists():
            with open(data_path / 'positions.json', 'r', encoding='utf-8') as f:
                positions = json.load(f)
            
            new_positions = positions.copy()
            for old_id, new_id in id_map.items():
                if old_id in positions:
                    pos_data = new_positions.pop(old_id)
                    
                    if new_id in new_positions:
                        print(f"⚠️ 持仓数据冲突: {new_id}, 保留原有持仓")
                    else:
                        new_positions[new_id] = pos_data
                        
            with open(data_path / 'positions.json', 'w', encoding='utf-8') as f:
                json.dump(new_positions, f, ensure_ascii=False, indent=2)
            print("✅ 持仓数据修复完成")

        # 4. 修复 orders.json
        if (data_path / 'orders.json').exists():
            with open(data_path / 'orders.json', 'r', encoding='utf-8') as f:
                orders = json.load(f)
            
            updated_orders_count = 0
            for order_id, order in orders.items():
                curr_uid = order.get('user_id')
                if curr_uid in id_map:
                    order['user_id'] = id_map[curr_uid]
                    updated_orders_count += 1
            
            with open(data_path / 'orders.json', 'w', encoding='utf-8') as f:
                json.dump(orders, f, ensure_ascii=False, indent=2)
            print(f"✅ 订单数据修复完成 (更新了 {updated_orders_count} 个订单)")

    except Exception as e:
        print(f"❌ 修复过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    fix_user_ids()
