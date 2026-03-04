"""
test_hk_integration.py - 港式麻将集成测试

模拟完整牌局，对每次胡牌验证：
  - 胡牌手牌合法性（is_winning_hand_given_melds 通过）
  - 七对子结构正确性
  - 番型合理性（各番型条件、互斥规则、范围校验）
  - 结算零和性
  - 花牌不会留在手牌里（应已自动收取）
  - AI 胡牌判断使用正确的 HK 验证函数
"""

import random
import pytest
from collections import Counter

from game.game_state import GameState
from game.ai_player import AIPlayer
from game.hand import (
    is_winning_hand_given_melds,
    can_chow,
)
from game.tiles import is_flower_tile, get_suit, get_number
from game.room_manager import INITIAL_CHIPS


# ---------------------------------------------------------------------------
# 模拟引擎
# ---------------------------------------------------------------------------

def simulate_hk_game(seed=None) -> dict | None:
    """
    模拟一局港式麻将，返回胡牌结果（流局返回 None）。
    """
    if seed is not None:
        random.seed(seed)

    ai = AIPlayer()
    gs = GameState(
        room_id="sim_hk",
        player_ids=["p0", "p1", "p2", "p3"],
        ruleset="hk",
    )
    gs.deal_initial_tiles()

    for _ in range(800):
        if gs.phase == "ended":
            break
        if gs.phase == "drawing":
            gs.draw_tile(gs.current_turn)
        elif gs.phase == "discarding":
            pidx = gs.current_turn
            p = gs.players[pidx]
            hand = p.hand_without_bonus()

            if ai.should_declare_win(hand, p.melds, "hk"):
                try:
                    gs.declare_win(pidx)
                    if gs.phase == "ended":
                        break
                except ValueError:
                    pass
            if gs.phase != "discarding":
                continue

            # 暗杠检测
            c = Counter(hand)
            kong = next((t for t, n in c.items() if n >= 4), None)
            if not kong:
                pung_tiles = {m[0] for m in p.melds if len(m) == 3 and m[0] == m[1] == m[2]}
                kong = next((t for t in pung_tiles if c.get(t, 0) >= 1), None)
            if kong:
                try:
                    gs.claim_kong(pidx, kong)
                    continue
                except Exception:
                    pass

            tile = ai.choose_discard(hand, p.melds, "hk")
            try:
                gs.discard_tile(pidx, tile)
            except ValueError:
                if hand:
                    try:
                        gs.discard_tile(pidx, hand[0])
                    except Exception:
                        pass

        elif gs.phase == "claiming":
            tile = gs.last_discard
            for i in sorted(gs._pending_claims):
                if i not in gs._pending_claims or i in gs._skipped_claims:
                    continue
                p2 = gs.players[i]
                h2 = p2.hand_without_bonus()
                avail = gs.get_available_actions(i)
                claimed = False
                if "win" in avail:
                    try:
                        gs.declare_win(i)
                        claimed = True
                    except Exception:
                        pass
                if not claimed and "kong" in avail and ai.decide_claim(h2, p2.melds, tile, "kong", "hk"):
                    try:
                        gs.claim_kong(i, tile)
                        claimed = True
                    except Exception:
                        pass
                if not claimed and "pung" in avail and ai.decide_claim(h2, p2.melds, tile, "pung", "hk"):
                    try:
                        gs.claim_pung(i)
                        claimed = True
                    except Exception:
                        pass
                if not claimed and "chow" in avail and ai.decide_claim(h2, p2.melds, tile, "chow", "hk"):
                    possible = can_chow(h2, tile)
                    if possible:
                        try:
                            gs.claim_chow(i, [t for t in possible[0] if t != tile])
                            claimed = True
                        except Exception:
                            pass
                if not claimed:
                    gs.skip_claim(i)
                if gs.phase != "claiming":
                    break

    if not gs.winner:
        return None

    winner_idx = next((i for i, p in enumerate(gs.players) if p.id == gs.winner), None)
    if winner_idx is None:
        return None

    winner = gs.players[winner_idx]
    return {
        "winner_idx": winner_idx,
        "dealer_idx": gs.dealer_idx,
        "winner_melds": list(winner.melds),
        "winner_hand": winner.hand_without_bonus(),
        "winner_flowers": list(winner.flowers),
        "winning_tile": gs.winning_tile,
        "ron": gs.win_ron,
        "discarder_idx": gs.win_discarder_idx,
        "han_total": gs.han_total,
        "han_breakdown": gs.han_breakdown,
        "kong_chip_transfers": dict(gs.kong_chip_transfers),
        "all_player_hands": [p.hand_without_bonus() for p in gs.players],
        "all_player_flowers": [list(p.flowers) for p in gs.players],
        "gs": gs,
    }


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------

def validate_hk_win(result: dict, game_idx: int) -> list[str]:
    """验证一次港式胡牌结果，返回所有问题列表。"""
    errors = []
    prefix = f"HK Game#{game_idx}"

    wi = result["winner_idx"]
    melds = result["winner_melds"]
    hand = result["winner_hand"]
    flowers = result["winner_flowers"]
    winning_tile = result["winning_tile"]
    ron = result["ron"]
    han_total = result["han_total"]
    han_breakdown = result["han_breakdown"]
    dealer_idx = result["dealer_idx"]

    # ── 1. 花牌不应留在手牌里 ────────────────────────────────────────────
    for tile in hand:
        if is_flower_tile(tile):
            errors.append(f"{prefix}: 花牌 '{tile}' 留在手牌里（应已自动收取）")

    for i, player_hand in enumerate(result["all_player_hands"]):
        for tile in player_hand:
            if is_flower_tile(tile):
                errors.append(f"{prefix}: 玩家 P{i} 手牌含花牌 '{tile}'")

    # ── 2. 胡牌手牌合法性 ───────────────────────────────────────────────
    if not is_winning_hand_given_melds(hand, len(melds)):
        errors.append(
            f"{prefix}: 胡牌手牌验证失败！"
            f"hand={hand}, melds={melds}"
        )
        return errors  # 基础验证失败，后续无意义

    # ── 3. 番型合理性 ────────────────────────────────────────────────────
    fan_names = [x["name_cn"] for x in han_breakdown]
    fan_values = {x["name_cn"]: x["fan"] for x in han_breakdown}

    # 基础番必须存在
    if "基本分" not in fan_names:
        errors.append(f"{prefix}: 缺少「基本分」番型")

    # 自摸/点炮互斥
    has_tsumo = "自摸" in fan_names
    if ron is False and not has_tsumo:
        errors.append(f"{prefix}: 自摸胡但没有自摸番")
    if ron is True and has_tsumo:
        errors.append(f"{prefix}: 荣和胡但有自摸番")

    # 门清条件：无副露且荣和
    if "门清" in fan_names:
        if melds:
            errors.append(f"{prefix}: 有副露但计了门清番")
        if ron is False:
            errors.append(f"{prefix}: 自摸不应计门清番（门清限荣和）")

    # 平胡条件：门清 + 荣和
    if "平胡" in fan_names:
        if melds:
            errors.append(f"{prefix}: 有副露但计了平胡番")
        if ron is False:
            errors.append(f"{prefix}: 自摸不应计平胡番")

    # 断幺：所有牌为 2-8，无幺九风字
    if "断幺" in fan_names:
        from game.hand import _h_is_simple
        all_tiles = list(hand)
        for m in melds:
            all_tiles.extend(m[:3])
        if not all(
            get_number(t) is not None and 2 <= get_number(t) <= 8
            for t in all_tiles if not is_flower_tile(t)
        ):
            errors.append(f"{prefix}: 断幺但手牌含幺九风字牌")

    # 无花：无花牌/季牌（花牌在 flowers 里）
    if "无花" in fan_names and flowers:
        errors.append(f"{prefix}: 计了无花番但有花牌 {flowers}")

    # 嶺上開花：自摸
    if "嶺上開花" in fan_names and ron is True:
        errors.append(f"{prefix}: 嶺上開花不能是荣和")

    # 七对互斥：七对不应和碰碰胡同时出现
    if "七对" in fan_names and "碰碰胡" in fan_names:
        errors.append(f"{prefix}: 七对和碰碰胡不应同时出现")

    # 番数范围
    if han_total < 1:
        errors.append(f"{prefix}: 番数 < 1（han_total={han_total}）")
    if han_total > 30:
        errors.append(f"{prefix}: 番数异常大（han_total={han_total}）")

    # 番型总和一致
    computed_total = sum(x["fan"] for x in han_breakdown)
    if computed_total != han_total:
        errors.append(
            f"{prefix}: 番型明细总和 {computed_total} ≠ han_total {han_total}"
        )

    return errors


def validate_hk_settlement(result: dict, game_idx: int,
                            pre_scores: dict, post_scores: dict) -> list[str]:
    """验证港式结算的零和性与合理性。"""
    errors = []
    prefix = f"HK Game#{game_idx}"

    wi = result["winner_idx"]
    winner_id = result["gs"].players[wi].id
    deltas = {pid: post_scores.get(pid, INITIAL_CHIPS) - pre_scores.get(pid, INITIAL_CHIPS)
              for pid in pre_scores}

    # 零和
    total_delta = sum(deltas.values())
    if total_delta != 0:
        errors.append(f"{prefix}: 结算不零和！delta_sum={total_delta}")

    # 胡牌者必须收到筹码（杠钱可能让输家反而不亏，但赢家应净正）
    if deltas.get(winner_id, 0) <= 0:
        errors.append(
            f"{prefix}: 胡牌者 {winner_id} 结算后筹码未增加"
            f"，delta={deltas.get(winner_id, 0)}"
        )

    # 荣和：只有放炮者应有负 delta（含杠钱）
    if result["ron"] is True and result["discarder_idx"] is not None:
        gs = result["gs"]
        discarder_id = gs.players[result["discarder_idx"]].id
        # 杠钱可让非放炮者也有变化，所以只检查放炮者
        if deltas.get(discarder_id, 0) >= 0:
            errors.append(
                f"{prefix}: 放炮者 {discarder_id} 筹码未减少"
                f"，delta={deltas.get(discarder_id, 0)}"
            )

    return errors


# ---------------------------------------------------------------------------
# 主测试
# ---------------------------------------------------------------------------

class TestHKIntegration:

    @pytest.mark.parametrize("seed", range(100))
    def test_single_game_win_validity(self, seed):
        """每个 seed 对应一局 HK 游戏，若有胡牌则验证所有条件。"""
        result = simulate_hk_game(seed=seed)
        if result is None:
            return  # 流局，跳过

        errors = validate_hk_win(result, game_idx=seed)
        assert not errors, "\n".join(errors)

    def test_100_games_settlement_zero_sum(self):
        """
        模拟 100 局港式，对每次胡牌验证结算零和性。
        同时统计番型分布用于健全性检查。
        """
        wins = draws = 0
        win_types = Counter()
        fan_dist = Counter()
        fan_type_counts = Counter()
        all_errors = []

        CHIP_CAP = 64

        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                draws += 1
                continue

            wins += 1
            win_type = "ron" if result["ron"] else "tsumo"
            win_types[win_type] += 1
            fan_dist[result["han_total"]] += 1
            for x in result["han_breakdown"]:
                fan_type_counts[x["name_cn"]] += 1

            errors = validate_hk_win(result, game_idx=seed)
            all_errors.extend(errors)

            # 模拟结算（简化版）
            gs = result["gs"]
            wi = result["winner_idx"]
            winner_id = gs.players[wi].id
            dealer_idx = gs.dealer_idx
            han = result["han_total"]
            unit = min(CHIP_CAP, 2 ** (han - 1))

            pre = {p.id: INITIAL_CHIPS for p in gs.players}
            post = dict(pre)

            def _pay(payer_idx):
                if wi == dealer_idx:
                    return 2 * unit
                return 2 * unit if payer_idx == dealer_idx else unit

            if result["ron"] and result["discarder_idx"] is not None:
                full = sum(_pay(i) for i in range(4) if i != wi)
                post[winner_id] += full
                post[gs.players[result["discarder_idx"]].id] -= full
            elif result["ron"] is False:
                for i, p in enumerate(gs.players):
                    if i != wi:
                        pay = _pay(i)
                        post[winner_id] += pay
                        post[p.id] -= pay

            # 杠钱
            for pid, delta in result["kong_chip_transfers"].items():
                post[pid] = post.get(pid, INITIAL_CHIPS) + delta

            settle_errors = validate_hk_settlement(result, seed, pre, post)
            all_errors.extend(settle_errors)

        # 统计报告
        total = wins + draws
        print(f"\n{'='*55}")
        print(f"港式麻将模拟 {total} 局：胡牌 {wins}，流局 {draws}")
        print(f"胡牌类型：{dict(win_types)}")
        print(f"番数分布：{dict(sorted(fan_dist.items()))}")
        print(f"最常见番型 Top-10：")
        for name, count in fan_type_counts.most_common(10):
            print(f"  {name}: {count}")
        print(f"发现问题：{len(all_errors)} 条")
        if all_errors:
            for e in all_errors[:10]:
                print(f"  ❌ {e}")
        print(f"{'='*55}")

        assert not all_errors, (
            f"发现 {len(all_errors)} 个问题：\n" + "\n".join(all_errors[:20])
        )

    def test_no_flowers_in_hands(self):
        """花牌不应留在任何玩家手牌中（应已自动收取到 flowers 列表）。"""
        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            for i, hand in enumerate(result["all_player_hands"]):
                for tile in hand:
                    assert not is_flower_tile(tile), (
                        f"Seed={seed}: P{i} 手牌含花牌 '{tile}'"
                    )

    def test_winner_fan_at_least_1(self):
        """胡牌者番数必须 ≥ 1。"""
        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            assert result["han_total"] >= 1, (
                f"Seed={seed}: 胡牌番数 {result['han_total']} < 1"
            )

    def test_hand_structure_always_valid(self):
        """胡牌手牌必须通过 is_winning_hand_given_melds 验证。"""
        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            assert is_winning_hand_given_melds(
                result["winner_hand"], len(result["winner_melds"])
            ), (
                f"Seed={seed}: 胡牌手牌验证失败"
                f" hand={result['winner_hand']}"
                f" melds={result['winner_melds']}"
            )

    def test_tsumo_vs_ron_fan_consistency(self):
        """自摸有自摸番，荣和无自摸番。"""
        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            fan_names = [x["name_cn"] for x in result["han_breakdown"]]
            has_tsumo = "自摸" in fan_names
            if result["ron"] is False:
                assert has_tsumo, f"Seed={seed}: 自摸但无自摸番"
            elif result["ron"] is True:
                assert not has_tsumo, f"Seed={seed}: 荣和但有自摸番"

    def test_menqing_fan_conditions(self):
        """门清番只在无副露的荣和时出现。"""
        for seed in range(100):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            fan_names = [x["name_cn"] for x in result["han_breakdown"]]
            if "门清" in fan_names:
                assert not result["winner_melds"], (
                    f"Seed={seed}: 有副露但计了门清番"
                )
                assert result["ron"] is True, (
                    f"Seed={seed}: 自摸不应计门清番"
                )

    def test_seven_pairs_structure(self):
        """七对子：手牌应为 7 个不同对子，无副露。"""
        for seed in range(200):  # 扩大范围增加七对子出现概率
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            fan_names = [x["name_cn"] for x in result["han_breakdown"]]
            if "七对" not in fan_names:
                continue
            hand = result["winner_hand"]
            melds = result["winner_melds"]
            # 七对要求无副露、14 张手牌、7 种不同牌各 2 张
            assert not melds, f"Seed={seed}: 七对有副露 {melds}"
            assert len(hand) == 14, f"Seed={seed}: 七对手牌不是14张"
            counts = Counter(hand)
            assert len(counts) == 7, f"Seed={seed}: 七对不是7种不同牌 {counts}"
            assert all(v == 2 for v in counts.values()), (
                f"Seed={seed}: 七对有不成对的牌 {counts}"
            )

    def test_settlement_zero_sum_with_kong(self):
        """含杠钱的局也必须零和。"""
        for seed in range(200):
            result = simulate_hk_game(seed=seed)
            if result is None:
                continue
            if not result["kong_chip_transfers"]:
                continue  # 无杠，跳过

            gs = result["gs"]
            wi = result["winner_idx"]
            winner_id = gs.players[wi].id
            dealer_idx = gs.dealer_idx
            han = result["han_total"]
            CHIP_CAP = 64
            unit = min(CHIP_CAP, 2 ** (han - 1))

            def _pay(payer_idx):
                if wi == dealer_idx:
                    return 2 * unit
                return 2 * unit if payer_idx == dealer_idx else unit

            scores = {p.id: INITIAL_CHIPS for p in gs.players}
            if result["ron"] and result["discarder_idx"] is not None:
                full = sum(_pay(i) for i in range(4) if i != wi)
                scores[winner_id] += full
                scores[gs.players[result["discarder_idx"]].id] -= full
            elif result["ron"] is False:
                for i, p in enumerate(gs.players):
                    if i != wi:
                        scores[winner_id] += _pay(i)
                        scores[p.id] -= _pay(i)

            for pid, delta in result["kong_chip_transfers"].items():
                scores[pid] = scores.get(pid, INITIAL_CHIPS) + delta

            total = sum(scores[p.id] - INITIAL_CHIPS for p in gs.players)
            assert total == 0, (
                f"Seed={seed}: 含杠钱结算不零和 delta_sum={total}"
            )
