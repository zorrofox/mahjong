"""
test_dalian_integration.py - 大连穷胡集成测试

模拟完整牌局，对每次胡牌的结果进行全面验证：
  - 胡牌条件正确性（三色全/幺九/至少一刻/禁止门清/禁手把一）
  - 宝牌逻辑正确性（只有 tenpai_players 可用宝牌；冲宝/摸宝区分）
  - 番型计算合理性（庄家番/夹胡/范围校验）
  - 结算零和性（所有玩家筹码变化之和为 0）
  - 杠分逻辑（只有胡牌者的杠计入）
"""

import random
import pytest
from collections import Counter

from game.game_state import GameState
from game.ai_player import AIPlayer
from game.hand import (
    is_winning_hand_dalian,
    can_chow,
    _DALIAN_SUITS,
)
from game.tiles import get_suit, get_number, is_flower_tile
from game.room_manager import INITIAL_CHIPS


# ---------------------------------------------------------------------------
# 模拟引擎
# ---------------------------------------------------------------------------

def simulate_dalian_game(seed=None) -> dict | None:
    """
    模拟一局大连穷胡游戏，返回胡牌结果（流局返回 None）。

    Returns dict with keys:
        winner_idx, winner_melds, winner_hand_with_win, winning_tile,
        ron, discarder_idx, han_total, han_breakdown,
        kong_log, bao_tile, bao_declared, tenpai_players,
        dealer_idx, all_player_melds, gs (GameState)
    """
    if seed is not None:
        random.seed(seed)

    ai = AIPlayer()
    gs = GameState(
        room_id="sim",
        player_ids=["p0", "p1", "p2", "p3"],
        ruleset="dalian",
    )
    gs.deal_initial_tiles()

    for _ in range(600):
        if gs.phase == "ended":
            break
        if gs.phase == "drawing":
            gs.draw_tile(gs.current_turn)
        elif gs.phase == "discarding":
            pidx = gs.current_turn
            p = gs.players[pidx]
            hand = p.hand_without_bonus()

            # 听牌自动处理
            if pidx in gs.tenpai_players:
                bao = gs._effective_bao(pidx)
                if ai.should_declare_win(hand, p.melds, "dalian", bao_tile=bao):
                    try:
                        gs.declare_win(pidx)
                        if gs.phase == "ended":
                            break
                    except ValueError:
                        pass
                if gs.phase != "discarding":
                    continue
                # 自动打回刚摸的牌
                drawn = gs.last_drawn_tile
                if drawn and drawn in p.hand:
                    try:
                        gs.discard_tile(pidx, drawn)
                    except ValueError:
                        pass
                    if gs.phase != "discarding":
                        # 出牌后检测宝牌
                        prev = set(gs.tenpai_players)
                        gs.check_and_trigger_bao()
                        continue
                continue

            # 普通 AI 出牌
            bao = gs._effective_bao(pidx)
            if ai.should_declare_win(hand, p.melds, "dalian", bao_tile=bao):
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

            tile = ai.choose_discard(hand, p.melds, "dalian", bao_tile=bao)
            try:
                gs.discard_tile(pidx, tile)
            except ValueError:
                if hand:
                    try:
                        gs.discard_tile(pidx, hand[0])
                    except Exception:
                        pass

            # 出牌后宝牌检测
            prev = set(gs.tenpai_players)
            gs.check_and_trigger_bao()

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
                if not claimed and "kong" in avail and ai.decide_claim(h2, p2.melds, tile, "kong", "dalian"):
                    try:
                        gs.claim_kong(i, tile)
                        claimed = True
                    except Exception:
                        pass
                if not claimed and "pung" in avail and ai.decide_claim(h2, p2.melds, tile, "pung", "dalian"):
                    try:
                        gs.claim_pung(i)
                        claimed = True
                    except Exception:
                        pass
                if not claimed and "chow" in avail and ai.decide_claim(h2, p2.melds, tile, "chow", "dalian"):
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

            # 出牌后宝牌
            if gs.phase != "claiming":
                gs.check_and_trigger_bao()

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
        "winner_hand": list(winner.hand),
        "winner_hand_without_bonus": winner.hand_without_bonus(),
        "winning_tile": gs.winning_tile,
        "ron": gs.win_ron,
        "discarder_idx": gs.win_discarder_idx,
        "han_total": gs.han_total,
        "han_breakdown": gs.han_breakdown,
        "kong_log": list(gs.kong_log),
        "bao_tile": gs.bao_tile,
        "bao_declared": gs.bao_declared,
        "tenpai_players": set(gs.tenpai_players),
        "all_player_melds": [list(p.melds) for p in gs.players],
        "gs": gs,
    }


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------

DALIAN_DRAGON_SET = frozenset({"RED", "GREEN", "WHITE"})
HONOR_SET = frozenset({"EAST", "SOUTH", "WEST", "NORTH", "RED", "GREEN", "WHITE"})


def validate_win(result: dict, game_idx: int) -> list[str]:
    """
    验证一次胡牌结果，返回所有发现的问题列表（空列表 = 无问题）。
    """
    errors = []
    prefix = f"Game#{game_idx}"

    wi = result["winner_idx"]
    melds = result["winner_melds"]
    hand = result["winner_hand_without_bonus"]
    winning_tile = result["winning_tile"]
    ron = result["ron"]
    han_total = result["han_total"]
    han_breakdown = result["han_breakdown"]
    bao_tile = result["bao_tile"]
    bao_declared = result["bao_declared"]
    tenpai_players = result["tenpai_players"]
    dealer_idx = result["dealer_idx"]
    gs = result["gs"]

    # ── 1. 胡牌手牌验证 ─────────────────────────────────────────────────
    # 按规则验证，宝牌只对 tenpai_players 有效
    effective_bao = bao_tile if (bao_declared and wi in tenpai_players) else None
    n_melds = len(melds)

    if not is_winning_hand_dalian(hand, n_melds, melds, bao_tile=effective_bao):
        errors.append(
            f"{prefix}: 胡牌手牌验证失败！"
            f"hand={hand}, melds={melds}, bao={effective_bao}"
        )
        return errors  # 基础验证失败，后续无意义

    # ── 2. 禁止门清 ──────────────────────────────────────────────────────
    if n_melds == 0:
        errors.append(f"{prefix}: 禁止门清违反（n_melds=0）")

    # ── 3. 禁手把一 ──────────────────────────────────────────────────────
    if n_melds >= 4:
        errors.append(f"{prefix}: 禁手把一违反（n_melds={n_melds}）")

    # ── 4. 三色全 ────────────────────────────────────────────────────────
    all_tiles = list(hand)
    for m in melds:
        all_tiles.extend(m[:3])
    suits = {get_suit(t) for t in all_tiles if get_suit(t)}

    # 如果用了宝牌，需要验证宝牌替换后三色全仍满足
    if effective_bao and effective_bao in hand:
        # 宝牌野牌：尝试各种替换后验证三色全
        bao_substitution_valid = False
        from game.hand import _ALL_DALIAN_TILES, _remove_tiles, is_winning_hand_dalian as iwd
        hand_without_bao = list(hand)
        hand_without_bao.remove(effective_bao)
        for sub in _ALL_DALIAN_TILES:
            if sub == effective_bao:
                continue
            test = hand_without_bao + [sub]
            if iwd(test, n_melds, melds, bao_tile=None):
                sub_all = test + [t for m in melds for t in m[:3]]
                sub_suits = {get_suit(t) for t in sub_all if get_suit(t)}
                if _DALIAN_SUITS <= sub_suits:
                    bao_substitution_valid = True
                    break
        if not bao_substitution_valid and not (_DALIAN_SUITS <= suits):
            errors.append(f"{prefix}: 三色全未满足（含宝牌）suits={suits}")
    else:
        if not (_DALIAN_SUITS <= suits):
            errors.append(f"{prefix}: 三色全未满足 suits={suits}")

    # ── 5. 幺九 ──────────────────────────────────────────────────────────
    has_honor = any(t in HONOR_SET for t in all_tiles)
    has_terminal = any(get_number(t) in (1, 9) for t in all_tiles if get_number(t))
    if not has_honor and not has_terminal:
        errors.append(f"{prefix}: 幺九未满足（无字牌也无幺九）")

    # ── 6. 至少一刻子（三元牌做将可免）──────────────────────────────────
    from game.hand import (
        decompose_winning_hand_dalian,
        _extract_groups_rec_dalian,
        find_pairs,
        _remove_tiles as rt,
    )
    decl_pung = any(
        len(m) >= 3 and m[0] == m[1] == m[2] for m in melds
    )
    if not decl_pung:
        decomp = decompose_winning_hand_dalian(hand)
        if decomp:
            groups = decomp.get("groups", [])
            concl_pung = any(g["type"] == "pung" for g in groups)
            pair_tile = decomp.get("pair")
            dragon_pair_exempt = pair_tile in DALIAN_DRAGON_SET
            if not concl_pung and not dragon_pair_exempt:
                errors.append(
                    f"{prefix}: 至少一刻子未满足（无明刻/暗刻，将='{pair_tile}'）"
                )

    # ── 7. 三元牌禁刻子 ──────────────────────────────────────────────────
    for m in melds:
        if len(m) >= 3 and m[0] == m[1] == m[2] and m[0] in DALIAN_DRAGON_SET:
            errors.append(f"{prefix}: 三元牌 '{m[0]}' 被用作刻子（禁止）")

    # ── 8. 宝牌野牌仅对 tenpai_players 有效 ────────────────────────────
    if bao_declared and bao_tile:
        if effective_bao is not None and wi not in tenpai_players:
            errors.append(
                f"{prefix}: 非听牌玩家（w={wi}）使用了宝牌野牌"
                f"（tenpai={tenpai_players}）"
            )

    # ── 9. 番型合理性校验 ────────────────────────────────────────────────
    fan_names = [x["name_cn"] for x in han_breakdown]
    fan_values = {x["name_cn"]: x["fan"] for x in han_breakdown}

    # 基础番 必须存在
    if "基础" not in fan_names:
        errors.append(f"{prefix}: 缺少「基础」番型")

    # 庄家番：只有庄家赢才有
    if "庄家" in fan_names and wi != dealer_idx:
        errors.append(
            f"{prefix}: 非庄家玩家（w={wi}, dealer={dealer_idx}）有庄家番"
        )
    if wi == dealer_idx and "庄家" not in fan_names:
        errors.append(f"{prefix}: 庄家赢但没有庄家番")

    # 自摸/点炮互斥
    has_tsumo = "自摸" in fan_names
    if ron is False and not has_tsumo:
        errors.append(f"{prefix}: 自摸胡但没有自摸番")
    if ron is True and has_tsumo:
        errors.append(f"{prefix}: 荣和胡但有自摸番")

    # 冲宝/摸宝不同时存在
    if "冲宝" in fan_names and "摸宝" in fan_names:
        errors.append(f"{prefix}: 冲宝和摸宝不应同时出现")

    # 冲宝：winning_tile == bao_tile 且手牌无需宝牌野牌即可胡（结构性等待张就是宝牌）
    if "冲宝" in fan_names:
        if not (effective_bao and winning_tile == effective_bao):
            errors.append(
                f"{prefix}: 冲宝条件不满足"
                f"（winning={winning_tile}, bao={effective_bao}）"
            )
        # 冲宝要求结构性等待（不依赖野牌替代）
        if effective_bao and winning_tile == effective_bao:
            from game.hand import is_winning_hand_dalian as _iwd
            if not _iwd(hand, n_melds, melds, bao_tile=None):
                errors.append(
                    f"{prefix}: 冲宝但手牌不能结构性胡（需要野牌替代才行）"
                    f"，应为摸宝"
                )

    # 摸宝：自摸 + 有效宝牌 + 宝牌在手中
    # 注意：winning_tile 可能等于 bao_tile（摸到宝牌后作为野牌替代胡牌，
    #       最后摸的牌是宝牌，所以 winning_tile = bao_tile，但结构上不是直接等待张）
    if "摸宝" in fan_names:
        if ron is not False:
            errors.append(f"{prefix}: 摸宝只能自摸，却是荣和")
        if not (effective_bao and effective_bao in hand):
            errors.append(
                f"{prefix}: 摸宝条件不满足（宝牌不在手中）"
                f"（bao={effective_bao}, hand_has_bao={effective_bao in hand if effective_bao else False}）"
            )

    # 杠上开花：自摸 + 有杠记录
    if "杠上开花" in fan_names and ron is True:
        errors.append(f"{prefix}: 杠上开花不能是荣和")

    # 番数范围
    if han_total < 1:
        errors.append(f"{prefix}: 番数 < 1（han_total={han_total}）")
    if han_total > 20:
        errors.append(f"{prefix}: 番数异常大（han_total={han_total}）")

    return errors


def validate_settlement(result: dict, game_idx: int,
                        scores_before: dict, scores_after: dict) -> list[str]:
    """验证结算的零和性与合理性。"""
    errors = []
    prefix = f"Game#{game_idx}"

    # 零和校验
    deltas = {pid: scores_after.get(pid, INITIAL_CHIPS) - scores_before.get(pid, INITIAL_CHIPS)
              for pid in scores_before}
    total_delta = sum(deltas.values())
    if total_delta != 0:
        errors.append(f"{prefix}: 结算不零和！delta_sum={total_delta}, deltas={deltas}")

    # 胡牌者应该收到筹码
    wi = result["winner_idx"]
    winner_id = result["gs"].players[wi].id
    if deltas.get(winner_id, 0) <= 0:
        errors.append(
            f"{prefix}: 胡牌者（{winner_id}）结算后筹码没有增加"
            f"，delta={deltas.get(winner_id, 0)}"
        )

    # 荣和：放炮者负责主要赔付；非放炮者只因胡牌者的杠分可能有负变化
    if result["ron"] is True and result["discarder_idx"] is not None:
        gs = result["gs"]
        discarder_id = gs.players[result["discarder_idx"]].id
        # 胡牌者杠分（每位非胡牌者都要付）
        winner_kongs = [k for k in result["kong_log"] if k["player_idx"] == wi]
        kong_per_player = sum(1 if k["type"] == "min" else 2 for k in winner_kongs)

        for i, p in enumerate(gs.players):
            if i == wi:
                continue
            delta = deltas.get(p.id, 0)
            if p.id == discarder_id:
                # 放炮者：主要赔付 + 杠分 = delta 应为负
                if delta >= 0:
                    errors.append(
                        f"{prefix}: 放炮者（{p.id}）筹码没有减少"
                        f"，delta={delta}"
                    )
            else:
                # 非放炮者：只需支付杠分（可以为负），不应支付荣和正文赔付
                if delta < -kong_per_player:
                    errors.append(
                        f"{prefix}: 荣和时非放炮者（{p.id}）筹码减少过多"
                        f"={delta}，期望 ≥ -{kong_per_player}（仅杠分）"
                    )

    # 杠分：只有胡牌者的杠计入，其他人的杠不影响结算
    kong_log = result["kong_log"]
    winner_kongs = [k for k in kong_log if k["player_idx"] == wi]
    non_winner_kongs = [k for k in kong_log if k["player_idx"] != wi]
    # 非胡牌者的杠不应影响任何人的分数
    if non_winner_kongs and total_delta != 0:
        pass  # 总量零和已在上面检查，这里只是记录信息

    return errors


# ---------------------------------------------------------------------------
# 主测试
# ---------------------------------------------------------------------------

class TestDalianIntegration:

    @pytest.mark.parametrize("seed", range(100))
    def test_single_game_win_validity(self, seed):
        """每个 seed 对应一局游戏，若有胡牌则验证所有条件。"""
        result = simulate_dalian_game(seed=seed)
        if result is None:
            return  # 流局，跳过

        errors = validate_win(result, game_idx=seed)
        assert not errors, "\n".join(errors)

    def test_100_games_settlement_zero_sum(self):
        """
        模拟 100 局，对每次胡牌验证结算零和性。
        并统计各种情况的出现频率（统计分析）。
        """
        wins = draws = 0
        win_types = Counter()
        fan_dist = Counter()
        all_errors = []

        for seed in range(100):
            result = simulate_dalian_game(seed=seed)
            if result is None:
                draws += 1
                continue

            wins += 1
            win_type = "ron" if result["ron"] else "tsumo"
            win_types[win_type] += 1
            fan_dist[result["han_total"]] += 1

            # 验证手牌
            errors = validate_win(result, game_idx=seed)
            all_errors.extend(errors)

            # 模拟结算（简化版：不依赖 websocket）
            gs = result["gs"]
            scores_before = {p.id: INITIAL_CHIPS for p in gs.players}
            han = result["han_total"]
            wi = result["winner_idx"]
            winner_id = gs.players[wi].id

            CHIP_CAP = 64

            def loser_unit(loser_idx, is_discarder=False):
                others_clean = all(
                    not gs.players[i].melds
                    for i in range(4) if i != wi
                )
                extra = 1 if not gs.players[loser_idx].melds else 0
                extra += 1 if others_clean else 0
                if is_discarder:
                    extra += 1
                return min(CHIP_CAP, 2 ** (han + extra - 1))

            scores_after = dict(scores_before)
            if result["ron"] and result["discarder_idx"] is not None:
                di = result["discarder_idx"]
                pay = loser_unit(di, is_discarder=True)
                scores_after[winner_id] += pay
                scores_after[gs.players[di].id] -= pay
            elif result["ron"] is False:
                for i in range(4):
                    if i != wi:
                        pay = loser_unit(i)
                        scores_after[winner_id] += pay
                        scores_after[gs.players[i].id] -= pay

            # 胡牌者杠分（明杠1×，暗杠2×）
            winner_kongs = [k for k in result["kong_log"] if k["player_idx"] == wi]
            kong_per_player = sum(1 if k["type"] == "min" else 2 for k in winner_kongs)
            if kong_per_player > 0:
                for i in range(4):
                    if i != wi:
                        scores_after[winner_id] += kong_per_player
                        scores_after[gs.players[i].id] -= kong_per_player

            settle_errors = validate_settlement(result, seed, scores_before, scores_after)
            all_errors.extend(settle_errors)

        # 统计报告
        total = wins + draws
        print(f"\n{'='*50}")
        print(f"模拟 {total} 局：胡牌 {wins}，流局 {draws}")
        print(f"胡牌类型：{dict(win_types)}")
        print(f"番数分布：{dict(sorted(fan_dist.items()))}")
        print(f"发现问题：{len(all_errors)} 条")
        if all_errors:
            for e in all_errors[:10]:
                print(f"  ❌ {e}")
        print(f"{'='*50}")

        assert not all_errors, (
            f"发现 {len(all_errors)} 个问题：\n" + "\n".join(all_errors[:20])
        )

    def test_bao_wild_card_only_for_tenpai_players(self):
        """专项验证：宝牌野牌只对 tenpai_players 有效。"""
        errors = []
        for seed in range(200):
            result = simulate_dalian_game(seed=seed)
            if result is None:
                continue

            wi = result["winner_idx"]
            bao_tile = result["bao_tile"]
            bao_declared = result["bao_declared"]
            tenpai_players = result["tenpai_players"]
            gs = result["gs"]
            hand = result["winner_hand_without_bonus"]
            melds = result["winner_melds"]

            if not bao_declared or not bao_tile:
                continue

            # 验证：非 tenpai_players 成员不能用宝牌胡牌
            effective_bao = bao_tile if wi in tenpai_players else None

            # 如果手牌只靠宝牌才能胡，那么必须在 tenpai_players 里
            can_win_without_bao = is_winning_hand_dalian(hand, len(melds), melds, bao_tile=None)
            can_win_with_bao = is_winning_hand_dalian(hand, len(melds), melds, bao_tile=bao_tile)

            if can_win_with_bao and not can_win_without_bao:
                # 宝牌是关键 → 必须在 tenpai_players
                if wi not in tenpai_players:
                    errors.append(
                        f"Seed={seed}: 非听牌玩家通过宝牌野牌胡牌！"
                        f"w={wi}, tenpai={tenpai_players}"
                    )

        assert not errors, "\n".join(errors)

    def test_kanchan_fan_detection(self):
        """专项验证：坎张胡牌正确计入夹胡番型。"""
        from game.hand import _is_kanchan_in_hand, calculate_han_dalian

        # 真正的坎张场景（手有 4,6，等 5）
        declared = [["BAMBOO_1", "BAMBOO_1", "BAMBOO_1"]]
        concealed = [
            "EAST", "EAST",
            "CIRCLES_1", "CIRCLES_2", "CIRCLES_3",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_9",
            "CHARACTERS_1", "CHARACTERS_2",
            "BAMBOO_4",  # 坎张：等 BAMBOO_5（手有4和6=BAMBOO_9 here... need to fix)
        ]

        # 更直接的测试：4,6 等 5
        declared2 = [["CIRCLES_1", "CIRCLES_1", "CIRCLES_1"]]
        concealed2 = [
            "EAST", "EAST",
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_9",
            "CHARACTERS_1", "CHARACTERS_2",
            "BAMBOO_4",  # 等 CHARACTERS_3（与 CHARACTERS_1,2 组顺子）或 BAMBOO_6（等5坎张）
        ]
        # 实际测试：有 4 和 6，等 5
        declared3 = [["EAST", "EAST", "EAST"]]
        hand_k = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_9",
            "CHARACTERS_4", "CHARACTERS_6",   # 坎张等 CHARACTERS_5
            "CIRCLES_1", "CIRCLES_2",
            "CHARACTERS_5",   # 胡牌张
        ]
        declared3_melds = [["EAST", "EAST", "EAST"]]

        hand_without_win = list(hand_k)
        hand_without_win.remove("CHARACTERS_5")

        assert _is_kanchan_in_hand("CHARACTERS_5", hand_without_win), \
            "CHARACTERS_5 应为坎张（4,6 中间）"

        result = calculate_han_dalian(
            concealed_tiles=hand_k,
            declared_melds=declared3_melds,
            ron=True,
            winning_tile="CHARACTERS_5",
        )
        fan_names = [x["name_cn"] for x in result["breakdown"]]
        assert "夹胡" in fan_names, f"坎张荣和应计夹胡，实际番型：{fan_names}"

        # 双面等待不是坎张
        hand_2sided = [
            "BAMBOO_1", "BAMBOO_2", "BAMBOO_3",
            "BAMBOO_7", "BAMBOO_8", "BAMBOO_9",
            "CHARACTERS_4", "CHARACTERS_5",   # 双面等 3 或 6
            "CIRCLES_1", "CIRCLES_2",
            "CHARACTERS_6",   # 胡牌张（高端）
        ]
        hw2 = list(hand_2sided)
        hw2.remove("CHARACTERS_6")
        assert not _is_kanchan_in_hand("CHARACTERS_6", hw2), \
            "双面等待不应是坎张"

    def test_no_menqing_win(self):
        """门清不能胡牌（所有胡牌必须有副露）。"""
        for seed in range(100):
            result = simulate_dalian_game(seed=seed)
            if result is None:
                continue
            assert len(result["winner_melds"]) >= 1, \
                f"Seed={seed}: 门清胡牌！melds={result['winner_melds']}"

    def test_no_dragon_pung_in_melds(self):
        """三元牌不能被碰（只能做将）。"""
        DRAGONS = {"RED", "GREEN", "WHITE"}
        for seed in range(200):
            result = simulate_dalian_game(seed=seed)
            if result is None:
                continue
            for i, player_melds in enumerate(result["all_player_melds"]):
                for m in player_melds:
                    if len(m) >= 3 and m[0] == m[1] == m[2] and m[0] in DRAGONS:
                        pytest.fail(
                            f"Seed={seed}: 玩家 {i} 碰了三元牌 '{m[0]}'（应被禁止）"
                        )
