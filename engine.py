#!/usr/bin/env python3
"""Experimental UCI chess engine with phase-aware evaluation and tactical search."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import chess
import chess.polyglot

from opening_book import choose_book_move

MATE = 30_000
MATE_THRESHOLD = 29_000
TB_WIN = 20_000
INF = 32_000
EXACT, LOWER, UPPER = 0, 1, 2
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}
PHASE_VALUE = {chess.KNIGHT: 1, chess.BISHOP: 1, chess.ROOK: 2, chess.QUEEN: 4}
MAX_PHASE = 24

_ENGINE_STYLE = "balanced"
_VALID_STYLES = {"balanced", "aggressive", "solid", "endgame"}


def _relative_square(square: chess.Square, color: chess.Color) -> chess.Square:
    return square if color == chess.WHITE else square ^ 56


def _pst(piece_type: chess.PieceType, square: chess.Square, color: chess.Color,
         endgame: bool) -> int:
    """Compact generated piece-square terms, in centipawns."""
    sq = _relative_square(square, color)
    file_index, rank_index = chess.square_file(sq), chess.square_rank(sq)
    center = 14 - abs(2 * file_index - 7) - abs(2 * rank_index - 7)
    if piece_type == chess.PAWN:
        return rank_index * (7 if endgame else 5) + center * 2
    if piece_type == chess.KNIGHT:
        return center * (5 if endgame else 6) - (8 if file_index in (0, 7) else 0)
    if piece_type == chess.BISHOP:
        return center * 3 + rank_index
    if piece_type == chess.ROOK:
        return rank_index * 2 + (8 if rank_index == 6 else 0)
    if piece_type == chess.QUEEN:
        return center * 2 if endgame else center
    if piece_type == chess.KING:
        return center * 5 if endgame else -center * 4 - rank_index * 2
    return 0


def _piece_mobility(board: chess.Board, color: chess.Color) -> int:
    """Pseudo-legal mobility for non-pawns, excluding squares occupied by friends."""
    own = board.occupied_co[color]
    total = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for square in board.pieces(piece_type, color):
            total += chess.popcount(board.attacks(square) & ~own)
    return total


def _effective_style() -> str:
    return _ENGINE_STYLE if _ENGINE_STYLE in _VALID_STYLES else "balanced"


def _apply_style_profile(board: chess.Board, score: int) -> int:
    style = _effective_style()
    phase = 0
    for piece in board.piece_map().values():
        phase += PHASE_VALUE.get(piece.piece_type, 0)
    phase = min(MAX_PHASE, phase)
    if style == "aggressive":
        score += 12 * (board.turn == chess.WHITE) * (not board.is_check())
        score += 6 * (_piece_mobility(board, chess.WHITE) - _piece_mobility(board, chess.BLACK))
        score += 10 if board.is_attacked_by(chess.WHITE, board.king(chess.BLACK)) else 0
        score += 7 * len(board.pieces(chess.QUEEN, chess.WHITE))
        if phase < 12:
            score += 10 * len(board.pieces(chess.PAWN, chess.WHITE))
    elif style == "solid":
        score += 18 * (board.is_check() and board.turn == chess.BLACK)
        score += 8 * (board.is_attacked_by(chess.BLACK, board.king(chess.WHITE)))
        score += 12 * (len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK)))
        score -= 5 * (_piece_mobility(board, chess.BLACK) - _piece_mobility(board, chess.WHITE))
    elif style == "endgame":
        if board.occupied_bitboard().bit_count() <= 12:
            score += 18 * (len(board.pieces(chess.PAWN, chess.WHITE)) - len(board.pieces(chess.PAWN, chess.BLACK)))
            score += 12 * (len(board.pieces(chess.QUEEN, chess.WHITE)) - len(board.pieces(chess.QUEEN, chess.BLACK)))
            score += 5 * (_piece_mobility(board, chess.WHITE) - _piece_mobility(board, chess.BLACK))
    return score


def evaluate(board: chess.Board) -> int:
    """Phase-aware white-perspective evaluation converted to side-to-move POV."""
    mg_score = 0
    eg_score = 0
    pawns = {chess.WHITE: [], chess.BLACK: []}
    phase = 0
    for piece in board.piece_map().values():
        phase += PHASE_VALUE.get(piece.piece_type, 0)
    phase = min(MAX_PHASE, phase)

    for square, piece in board.piece_map().items():
        color, kind = piece.color, piece.piece_type
        sign = 1 if color == chess.WHITE else -1
        value = PIECE_VALUE[kind]
        mg_score += sign * (value + _pst(kind, square, color, False))
        eg_score += sign * (value + _pst(kind, square, color, True))
        if kind == chess.PAWN:
            pawns[color].append(square)

    for color in (chess.WHITE, chess.BLACK):
        sign = 1 if color == chess.WHITE else -1
        our_pawns = pawns[color]
        enemy_pawns = pawns[not color]
        files = [chess.square_file(square) for square in our_pawns]
        for file_index in range(8):
            count = files.count(file_index)
            if count > 1:
                mg_score -= sign * 13 * (count - 1)
                eg_score -= sign * 16 * (count - 1)

        for square in our_pawns:
            file_index = chess.square_file(square)
            rank_index = chess.square_rank(_relative_square(square, color))
            if not any(abs(other_file - file_index) == 1 for other_file in files):
                mg_score -= sign * 12
                eg_score -= sign * 10

            passed = not any(
                abs(chess.square_file(enemy_sq) - file_index) <= 1
                and chess.square_rank(_relative_square(enemy_sq, not color)) > 7 - rank_index
                for enemy_sq in enemy_pawns
            )
            if passed:
                bonus = 8 + rank_index * rank_index * 3
                mg_score += sign * bonus
                eg_score += sign * (bonus * 2)

            if any(abs(chess.square_file(other) - file_index) == 1
                   and abs(chess.square_rank(_relative_square(other, color)) - rank_index) <= 1
                   for other in our_pawns if other != square):
                mg_score += sign * 5
                eg_score += sign * 10

        bishops = board.pieces(chess.BISHOP, color)
        if len(bishops) >= 2:
            mg_score += sign * 28
            eg_score += sign * 40

        for rook_square in board.pieces(chess.ROOK, color):
            file_index = chess.square_file(rook_square)
            if not any(chess.square_file(p) == file_index for p in our_pawns):
                mg_score += sign * (18 if not any(chess.square_file(p) == file_index for p in enemy_pawns) else 10)
            if chess.square_rank(_relative_square(rook_square, color)) == 6:
                mg_score += sign * 12
                eg_score += sign * 16

        for knight_square in board.pieces(chess.KNIGHT, color):
            rel = _relative_square(knight_square, color)
            rank_index = chess.square_rank(rel)
            file_index = chess.square_file(rel)
            supported = any(
                chess.square_file(p) in (file_index - 1, file_index + 1)
                and chess.square_rank(_relative_square(p, color)) == rank_index - 1
                for p in our_pawns
            )
            challengeable = any(
                abs(chess.square_file(p) - file_index) <= 1
                and chess.square_rank(_relative_square(p, not color)) > 7 - rank_index
                for p in enemy_pawns
            )
            if rank_index >= 3 and supported and not challengeable:
                mg_score += sign * 18
                eg_score += sign * 12

        king = board.king(color)
        if king is not None and phase >= 8:
            king_file, king_rank = chess.square_file(king), chess.square_rank(king)
            forward = 1 if color == chess.WHITE else -1
            shield = 0
            for df in (-1, 0, 1):
                f, r = king_file + df, king_rank + forward
                if 0 <= f < 8 and 0 <= r < 8 and board.piece_at(chess.square(f, r)) == chess.Piece(chess.PAWN, color):
                    shield += 1
            mg_score += sign * (shield * 8 - (3 - shield) * 5)
            ring = chess.SquareSet()
            for f in range(max(0, king_file - 1), min(7, king_file + 1) + 1):
                for r in range(max(0, king_rank - 1), min(7, king_rank + 1) + 1):
                    ring.add(chess.square(f, r))
            pressure = 0
            for enemy_square, enemy_piece in board.piece_map().items():
                if enemy_piece.color != color and enemy_piece.piece_type != chess.KING:
                    pressure += chess.popcount(board.attacks(enemy_square) & ring)
            mg_score -= sign * min(36, pressure * 3)

    mg_score += 2 * (_piece_mobility(board, chess.WHITE) - _piece_mobility(board, chess.BLACK))
    for square, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        color = piece.color
        attackers = board.attackers(not color, square)
        if not attackers:
            continue
        defenders = board.attackers(color, square)
        if not defenders:
            penalty = min(45, PIECE_VALUE[piece.piece_type] // 10)
            mg_score += -penalty if color == chess.WHITE else penalty

    blended = (mg_score * phase + eg_score * (MAX_PHASE - phase)) // MAX_PHASE
    score = blended if board.turn == chess.WHITE else -blended
    return _apply_style_profile(board, score)


def score_to_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score + ply
    if score < -MATE_THRESHOLD:
        return score - ply
    return score


def score_from_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score - ply
    if score < -MATE_THRESHOLD:
        return score + ply
    return score


@dataclass
class SearchLimits:
    max_depth: int = 64
    deadline: Optional[float] = None
    max_nodes: Optional[int] = None


@dataclass
class TTEntry:
    depth: int
    score: int
    flag: int
    move: Optional[chess.Move]
    age: int


class SearchStopped(Exception):
    pass


class Searcher:
    def __init__(self, stop_event: threading.Event, info_callback=None,
                 tt: Optional[dict] = None, max_tt_entries: int = 40_000,
                 tablebase=None, age: int = 0):
        self.stop_event = stop_event
        self.info_callback = info_callback
        self.nodes = 0
        self.tt: dict[tuple[int, int], TTEntry] = tt if tt is not None else {}
        self.max_tt_entries = max_tt_entries
        self.tablebase = tablebase
        self.age = age
        self.killers: dict[int, list[chess.Move]] = {}
        self.history: dict[tuple[bool, chess.Move], int] = {}
        self.countermoves: dict[tuple[bool, int, int], chess.Move] = {}
        self.pv: dict[int, list[chess.Move]] = {}
        self.limits = SearchLimits()

    def check_stop(self) -> None:
        if self.stop_event.is_set():
            raise SearchStopped
        if self.limits.deadline is not None and time.monotonic() >= self.limits.deadline:
            raise SearchStopped
        if self.limits.max_nodes is not None and self.nodes >= self.limits.max_nodes:
            raise SearchStopped

    @staticmethod
    def position_key(board: chess.Board) -> tuple[int, int]:
        return chess.polyglot.zobrist_hash(board), min(board.halfmove_clock, 100)

    def terminal_score(self, board: chess.Board, ply: int) -> Optional[int]:
        if board.is_checkmate():
            return -MATE + ply
        if (board.is_stalemate() or board.is_insufficient_material() or
                board.is_fifty_moves() or board.can_claim_threefold_repetition()):
            return 0
        return None

    def tablebase_score(self, board: chess.Board, ply: int) -> Optional[int]:
        if self.tablebase is None or board.occupied.bit_count() > 7 or board.halfmove_clock >= 90:
            return None
        try:
            wdl = self.tablebase.probe_wdl(board)
        except (KeyError, OSError, chess.syzygy.MissingTableError):
            return None
        if wdl > 0:
            return TB_WIN - ply
        if wdl < 0:
            return -TB_WIN + ply
        return 0

    def move_order_score(self, board: chess.Board, move: chess.Move, ply: int,
                         tt_move: Optional[chess.Move]) -> int:
        if move == tt_move:
            return 2_000_000
        if move.promotion:
            return 1_500_000 + PIECE_VALUE[move.promotion]
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            victim_value = PIECE_VALUE[victim.piece_type] if victim else PIECE_VALUE[chess.PAWN]
            attacker = board.piece_at(move.from_square)
            attacker_value = PIECE_VALUE[attacker.piece_type] if attacker else 0
            score = 1_000_000 + victim_value * 10 - attacker_value
            if board.gives_check(move):
                score += 50_000
            return score
        if board.gives_check(move):
            return 900_000
        killers = self.killers.get(ply, [])
        if move in killers:
            return 800_000 - killers.index(move)
        if board.move_stack:
            previous = board.peek()
            if move == self.countermoves.get((board.turn, previous.from_square, previous.to_square)):
                return 750_000
        return self.history.get((board.turn, move), 0)

    def ordered_moves(self, board: chess.Board, ply: int, tt_move=None):
        return sorted(board.legal_moves,
                      key=lambda move: self.move_order_score(board, move, ply, tt_move), reverse=True)

    def quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int, qply: int = 0) -> int:
        self.nodes += 1
        if (self.nodes & 127) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        tb_score = self.tablebase_score(board, ply)
        if tb_score is not None:
            return tb_score
        in_check = board.is_check()
        if qply >= 16:
            if not in_check:
                return evaluate(board)
            evasions = list(board.legal_moves)
            if not evasions:
                return -MATE + ply
            best = -INF
            for move in evasions:
                board.push(move)
                try:
                    value = -self.terminal_score(board, ply + 1) if board.is_checkmate() else -evaluate(board)
                finally:
                    board.pop()
                best = max(best, value)
            return best

        if not in_check:
            stand_pat = evaluate(board)
            if stand_pat >= beta:
                return beta
            alpha = max(alpha, stand_pat)
            moves = [move for move in board.legal_moves if board.is_capture(move) or move.promotion]
        else:
            moves = list(board.legal_moves)

        for move in sorted(moves, key=lambda m: self.move_order_score(board, m, ply, None), reverse=True):
            board.push(move)
            try:
                value = -self.quiescence(board, -beta, -alpha, ply + 1, qply + 1)
            finally:
                board.pop()
            if value >= beta:
                return beta
            alpha = max(alpha, value)
        return alpha

    def _can_null_prune(self, board: chess.Board, depth: int, beta: int) -> bool:
        if depth < 3 or board.is_check() or beta >= MATE_THRESHOLD or board.halfmove_clock >= 90:
            return False
        if board.move_stack and board.peek().is_null():
            return False
        rooks_queens = board.pieces_mask(chess.ROOK, board.turn) | board.pieces_mask(chess.QUEEN, board.turn)
        minors = board.pieces_mask(chess.KNIGHT, board.turn) | board.pieces_mask(chess.BISHOP, board.turn)
        return bool(rooks_queens or chess.popcount(minors) >= 2)

    def _store_tt(self, key, entry: TTEntry) -> None:
        old = self.tt.get(key)
        if old is not None and old.depth > entry.depth and old.age == self.age and entry.flag != EXACT:
            return
        if len(self.tt) >= self.max_tt_entries and key not in self.tt:
            victims = sorted(self.tt, key=lambda item: (self.tt[item].age == self.age, self.tt[item].depth))
            for victim in victims[:max(1, self.max_tt_entries // 16)]:
                del self.tt[victim]
        self.tt[key] = entry

    def _remember_quiet_cutoff(self, board: chess.Board, move: chess.Move, ply: int, depth: int) -> None:
        killers = self.killers.setdefault(ply, [])
        if move not in killers:
            killers.insert(0, move)
            del killers[2:]
        history_key = (board.turn, move)
        self.history[history_key] = min(100_000, self.history.get(history_key, 0) + depth * depth)
        if board.move_stack:
            previous = board.peek()
            self.countermoves[(board.turn, previous.from_square, previous.to_square)] = move

    def negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if (self.nodes & 127) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        tb_score = self.tablebase_score(board, ply)
        if tb_score is not None:
            return tb_score
        if board.is_check():
            depth += 1
        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply)

        original_alpha, original_beta = alpha, beta
        key = self.position_key(board)
        path_dependent = board.is_repetition(2)
        entry = None if path_dependent else self.tt.get(key)
        tt_move = None
        if entry:
            tt_move = entry.move
            tt_score = score_from_tt(entry.score, ply)
            if entry.depth >= depth:
                if entry.flag == EXACT or (entry.flag == LOWER and tt_score >= beta) or (entry.flag == UPPER and tt_score <= alpha):
                    return tt_score

        if self._can_null_prune(board, depth, beta):
            reduction = 2 + depth // 6
            board.push(chess.Move.null())
            try:
                null_score = -self.negamax(board, depth - 1 - reduction, -beta, -beta + 1, ply + 1)
            finally:
                board.pop()
            if null_score >= beta:
                return null_score

        best_score, best_move = -INF, None
        moves = self.ordered_moves(board, ply, tt_move)
        for index, move in enumerate(moves):
            quiet = not board.is_capture(move) and not move.promotion
            gives_check = board.gives_check(move)
            board.push(move)
            self.pv[ply + 1] = []
            try:
                if index == 0:
                    value = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
                else:
                    reduction = 1 if depth >= 3 and index >= 3 and quiet and not gives_check else 0
                    value = -self.negamax(board, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
                    if value > alpha and reduction:
                        value = -self.negamax(board, depth - 1, -alpha - 1, -alpha, ply + 1)
                    if alpha < value < beta:
                        value = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.pop()

            if value > best_score:
                best_score, best_move = value, move
                self.pv[ply] = [move] + self.pv.get(ply + 1, [])
            alpha = max(alpha, value)
            if alpha >= beta:
                if quiet:
                    self._remember_quiet_cutoff(board, move, ply, depth)
                break

        if best_move is None:
            return 0
        if not path_dependent:
            flag = UPPER if best_score <= original_alpha else LOWER if best_score >= original_beta else EXACT
            self._store_tt(key, TTEntry(depth, score_to_tt(best_score, ply), flag, best_move, self.age))
        return best_score

    def search_root(self, board: chess.Board, depth: int, alpha: int, beta: int):
        original_alpha, original_beta = alpha, beta
        best_score, best_move = -INF, next(iter(board.legal_moves))
        key = self.position_key(board)
        entry = self.tt.get(key)
        moves = self.ordered_moves(board, 0, entry.move if entry else None)
        for index, move in enumerate(moves):
            self.check_stop()
            board.push(move)
            self.pv[1] = []
            try:
                if index == 0:
                    value = -self.negamax(board, depth - 1, -beta, -alpha, 1)
                else:
                    value = -self.negamax(board, depth - 1, -alpha - 1, -alpha, 1)
                    if alpha < value < beta:
                        value = -self.negamax(board, depth - 1, -beta, -alpha, 1)
            finally:
                board.pop()
            if value > best_score:
                best_score, best_move = value, move
                self.pv[0] = [move] + self.pv.get(1, [])
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        flag = UPPER if best_score <= original_alpha else LOWER if best_score >= original_beta else EXACT
        self._store_tt(key, TTEntry(depth, score_to_tt(best_score, 0), flag, best_move, self.age))
        return best_score, best_move, self.pv.get(0, [best_move])

    def run(self, board: chess.Board, limits: SearchLimits) -> chess.Move:
        self.limits = limits
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return chess.Move.null()
        best_move = legal_moves[0]
        previous_score = 0
        started = time.monotonic()
        for depth in range(1, limits.max_depth + 1):
            window = 50 if depth > 1 else INF
            alpha, beta = max(-INF, previous_score - window), min(INF, previous_score + window)
            try:
                while True:
                    self.pv.clear()
                    score, candidate, pv = self.search_root(board, depth, alpha, beta)
                    if score <= alpha and alpha > -INF:
                        window *= 2
                        alpha = max(-INF, previous_score - window)
                        continue
                    if score >= beta and beta < INF:
                        window *= 2
                        beta = min(INF, previous_score + window)
                        continue
                    break
            except SearchStopped:
                break
            best_move, previous_score = candidate, score
            elapsed_ms = max(1, int((time.monotonic() - started) * 1000))
            if self.info_callback:
                self.info_callback(depth, score, self.nodes, elapsed_ms, pv)
            if abs(score) >= MATE - depth:
                break
        return best_move


_output_lock = threading.Lock()
_state_lock = threading.Lock()
_board = chess.Board()
_worker: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_hash_mb = 16
_move_overhead_ms = 30
_use_book = True
_tt: dict[tuple[int, int], TTEntry] = {}
_tt_age = 0
_tablebase = None
_tablebase_path = ""


def send(line: str) -> None:
    with _output_lock:
        print(line, flush=True)


def parse_go(tokens: list[str], board: Optional[chess.Board] = None) -> SearchLimits:
    values: dict[str, int] = {}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in {"infinite", "ponder"}:
            values[token] = 1
            i += 1
        elif token in {"wtime", "btime", "winc", "binc", "movestogo", "depth", "nodes", "movetime"} and i + 1 < len(tokens):
            try:
                values[token] = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    max_depth = max(1, min(values.get("depth", 64), 64))
    max_nodes = max(1, values["nodes"]) if "nodes" in values else None
    deadline = None
    if "movetime" in values:
        deadline = time.monotonic() + max(0.001, (values["movetime"] - _move_overhead_ms) / 1000)
    elif "infinite" not in values and ("wtime" in values or "btime" in values):
        turn = board.turn if board is not None else _board.turn
        remaining = max(1, values.get("wtime" if turn == chess.WHITE else "btime", 1_000))
        increment = max(0, values.get("winc" if turn == chess.WHITE else "binc", 0))
        usable = max(1, remaining - _move_overhead_ms)
        allocation = max(1, min(usable * 0.7, usable / max(1, values.get("movestogo", 30)) + increment * 0.8))
        deadline = time.monotonic() + allocation / 1000
    return SearchLimits(max_depth, deadline, max_nodes)


def stop_search() -> None:
    global _worker, _stop_event
    worker, event = _worker, _stop_event
    if event:
        event.set()
    if worker and worker.is_alive() and worker is not threading.current_thread():
        worker.join()
    _worker = None
    _stop_event = None


def start_search(tokens: list[str]) -> None:
    global _worker, _stop_event, _tt_age
    stop_search()
    with _state_lock:
        board = _board.copy(stack=True)
    if _use_book:
        book_move = choose_book_move(board)
        if book_move is not None:
            send(f"info string opening book move {book_move.uci()}")
            send(f"bestmove {book_move.uci()}")
            return
    limits = parse_go(tokens, board)
    event = threading.Event()
    _stop_event = event
    _tt_age += 1
    age = _tt_age

    def report(depth, score, nodes, elapsed_ms, pv):
        if abs(score) >= MATE_THRESHOLD:
            mate = max(1, (MATE - abs(score) + 1) // 2)
            score_text = f"mate {mate if score > 0 else -mate}"
        else:
            score_text = f"cp {score}"
        pv_text = " ".join(move.uci() for move in pv)
        send(f"info depth {depth} score {score_text} nodes {nodes} nps {nodes * 1000 // max(1, elapsed_ms)} time {elapsed_ms} pv {pv_text}".rstrip())

    def work():
        searcher = Searcher(event, report, _tt, max(1_000, _hash_mb * 1_500), _tablebase, age)
        best = searcher.run(board, limits)
        send(f"bestmove {best.uci()}")

    _worker = threading.Thread(target=work, daemon=True)
    _worker.start()


def set_position(tokens: list[str]) -> None:
    global _board
    try:
        if len(tokens) < 2:
            return
        if tokens[1] == "startpos":
            board, index = chess.Board(), 2
        elif tokens[1] == "fen" and len(tokens) >= 8:
            board, index = chess.Board(" ".join(tokens[2:8])), 8
        else:
            raise ValueError("expected startpos or fen")
        if index < len(tokens) and tokens[index] == "moves":
            for uci in tokens[index + 1:]:
                board.push_uci(uci)
        with _state_lock:
            _board = board
    except (ValueError, IndexError) as exc:
        send(f"info string Invalid position command: {exc}")


def set_option(tokens: list[str]) -> None:
    global _hash_mb, _move_overhead_ms, _use_book, _tablebase, _tablebase_path, _ENGINE_STYLE
    try:
        name_index = tokens.index("name") + 1
        value_index = tokens.index("value")
        name = " ".join(tokens[name_index:value_index]).lower()
        value = " ".join(tokens[value_index + 1:])
        if name == "hash":
            _hash_mb = max(1, min(int(value), 256))
            _tt.clear()
        elif name == "move overhead":
            _move_overhead_ms = max(0, min(int(value), 5_000))
        elif name == "use book":
            _use_book = value.lower() in {"true", "1", "on", "yes"}
        elif name == "style":
            normalized = value.lower().strip()
            if normalized in _VALID_STYLES:
                _ENGINE_STYLE = normalized
                send(f"info string style set to {normalized}")
        elif name == "syzygypath":
            if _tablebase is not None:
                _tablebase.close()
                _tablebase = None
            _tablebase_path = value.strip()
            if _tablebase_path:
                try:
                    _tablebase = chess.syzygy.open_tablebase(_tablebase_path)
                    send(f"info string Syzygy tablebases loaded from {_tablebase_path}")
                except (OSError, ValueError) as exc:
                    _tablebase_path = ""
                    send(f"info string Could not load Syzygy tablebases: {exc}")
    except (ValueError, IndexError):
        return


def main() -> None:
    for raw_line in sys.stdin:
        tokens = raw_line.strip().split()
        if not tokens:
            continue
        command = tokens[0]
        if command == "uci":
            send("id name Chess_Bot Python")
            send("id author maciekglow11-design")
            send("option name Hash type spin default 16 min 1 max 256")
            send("option name Move Overhead type spin default 30 min 0 max 5000")
            send("option name Use Book type check default true")
            send("option name Style type combo default balanced var balanced var aggressive var solid var endgame")
            send("option name SyzygyPath type string default")
            send("uciok")
        elif command == "isready":
            send("readyok")
        elif command == "ucinewgame":
            stop_search()
            _tt.clear()
        elif command == "position":
            stop_search()
            set_position(tokens)
        elif command == "go":
            start_search(tokens)
        elif command == "stop":
            stop_search()
        elif command == "setoption":
            set_option(tokens)
        elif command == "quit":
            stop_search()
            if _tablebase is not None:
                _tablebase.close()
            break


if __name__ == "__main__":
    main()




