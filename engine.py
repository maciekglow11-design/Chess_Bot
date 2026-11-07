#!/usr/bin/env python3
"""A small UCI chess engine with alpha-beta search and a hand-crafted evaluation."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import chess
import chess.polyglot

MATE = 30_000
MATE_THRESHOLD = 29_000
INF = 32_000
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def evaluate(board: chess.Board) -> int:
    """Return a centipawn evaluation from the side-to-move's perspective."""
    score = 0
    pawns = {chess.WHITE: [], chess.BLACK: []}
    non_pawn_material = 0

    for square, piece in board.piece_map().items():
        color = piece.color
        sign = 1 if color == chess.WHITE else -1
        kind = piece.piece_type
        value = PIECE_VALUE[kind]
        file_index = chess.square_file(square)
        rank_index = chess.square_rank(square)
        relative_rank = rank_index if color == chess.WHITE else 7 - rank_index
        center_distance = abs(2 * file_index - 7) + abs(2 * rank_index - 7)
        center = 14 - center_distance  # 0..14, higher near the center

        score += sign * value
        if kind == chess.PAWN:
            pawns[color].append(square)
            score += sign * (relative_rank * 7 + center * 2)
        elif kind == chess.KNIGHT:
            score += sign * center * 5
            non_pawn_material += value
        elif kind == chess.BISHOP:
            score += sign * center * 3
            non_pawn_material += value
        elif kind == chess.ROOK:
            score += sign * relative_rank * 2
            non_pawn_material += value
        elif kind == chess.QUEEN:
            score += sign * center
            non_pawn_material += value
        elif kind == chess.KING:
            # Keep the king sheltered in the middlegame; centralize it in endings.
            if non_pawn_material < 2_000:
                score += sign * center * 4
            else:
                score -= sign * center * 3

    for color in (chess.WHITE, chess.BLACK):
        sign = 1 if color == chess.WHITE else -1
        files = [chess.square_file(sq) for sq in pawns[color]]
        for file_index in range(8):
            count = files.count(file_index)
            if count > 1:
                score -= sign * 12 * (count - 1)  # doubled pawns
        for square in pawns[color]:
            file_index = chess.square_file(square)
            if not any(abs(other_file - file_index) == 1 for other_file in files):
                score -= sign * 10  # isolated pawn
            relative_rank = chess.square_rank(square) if color == chess.WHITE else 7 - chess.square_rank(square)
            enemy_pawns = pawns[not color]
            passed = True
            for enemy_sq in enemy_pawns:
                enemy_file = chess.square_file(enemy_sq)
                enemy_rank = chess.square_rank(enemy_sq) if color == chess.WHITE else 7 - chess.square_rank(enemy_sq)
                if abs(enemy_file - file_index) <= 1 and enemy_rank > relative_rank:
                    passed = False
                    break
            if passed:
                score += sign * (10 + relative_rank * relative_rank * 2)

        bishops = board.pieces(chess.BISHOP, color)
        if len(bishops) >= 2:
            score += sign * 28

    return (score if board.turn == chess.WHITE else -score) + 10  # tempo bonus


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


class SearchStopped(Exception):
    pass


class Searcher:
    def __init__(self, stop_event: threading.Event, info_callback=None):
        self.stop_event = stop_event
        self.info_callback = info_callback
        self.nodes = 0
        self.tt: dict[int, tuple[int, int, int, Optional[chess.Move]]] = {}
        self.killers: dict[int, list[chess.Move]] = {}
        self.history: dict[tuple[bool, chess.Move], int] = {}
        self.pv: dict[int, list[chess.Move]] = {}
        self.limits = SearchLimits()

    def check_stop(self) -> None:
        if self.stop_event.is_set():
            raise SearchStopped
        if self.limits.deadline is not None and time.monotonic() >= self.limits.deadline:
            raise SearchStopped
        if self.limits.max_nodes is not None and self.nodes >= self.limits.max_nodes:
            raise SearchStopped

    def terminal_score(self, board: chess.Board, ply: int) -> Optional[int]:
        if board.is_checkmate():
            return -MATE + ply
        if (board.is_stalemate() or board.is_insufficient_material() or
                board.is_fifty_moves() or board.can_claim_threefold_repetition()):
            return 0
        return None

    def move_order_score(self, board: chess.Board, move: chess.Move, ply: int,
                         tt_move: Optional[chess.Move]) -> int:
        if move == tt_move:
            return 2_000_000
        if move.promotion:
            return 1_000_000 + PIECE_VALUE[move.promotion]
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            # En passant captures a pawn on a different square.
            victim_value = PIECE_VALUE[victim.piece_type] if victim else PIECE_VALUE[chess.PAWN]
            attacker = board.piece_at(move.from_square)
            attacker_value = PIECE_VALUE[attacker.piece_type] if attacker else 0
            return 900_000 + victim_value * 10 - attacker_value
        killers = self.killers.get(ply, [])
        if move in killers:
            return 800_000 - killers.index(move)
        return self.history.get((board.turn, move), 0)

    def ordered_moves(self, board: chess.Board, ply: int, tt_move=None):
        return sorted(board.legal_moves,
                      key=lambda move: self.move_order_score(board, move, ply, tt_move),
                      reverse=True)

    def quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int, qply: int = 0) -> int:
        self.nodes += 1
        if (self.nodes & 1023) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        in_check = board.is_check()
        if qply >= 16:
            return evaluate(board)
        if not in_check:
            stand_pat = evaluate(board)
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat
            moves = [m for m in board.legal_moves if board.is_capture(m) or m.promotion]
        else:
            moves = list(board.legal_moves)

        for move in sorted(moves, key=lambda m: self.move_order_score(board, m, ply, None), reverse=True):
            board.push(move)
            try:
                score = -self.quiescence(board, -beta, -alpha, ply + 1, qply + 1)
            finally:
                board.pop()
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if (self.nodes & 1023) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply)

        original_alpha = alpha
        key = chess.polyglot zobrist_hash(board)
        tt_entry = self.tt.get(key)
        tt_move = None
        if tt_entry is not None:
            tt_depth, tt_score, tt_flag, tt_move = tt_entry
            tt_score = score_from_tt(tt_score, ply)
            if tt_depth >= depth:
                if tt_flag == 0:
                    return tt_score
                if tt_flag == 1 and tt_score >= beta:  # lower bound
                    return tt_score
                if tt_flag == 2 and tt_score <= alpha:  # upper bound
                    return tt_score

        best_score = -INF
        best_move = None
        for move in self.ordered_moves(board, ply, tt_move):
            board.push(move)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.pop()
            if score > best_score:
                best_score = score
                best_move = move
                self.pv[ply] = [move] + self.pv.get(ply + 1, [])
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not board.is_capture(move) and not move.promotion:
                    killers = self.killers.setdefault(ply, [])
                    if move not in killers:
                        killers.insert(0, move)
                        del killers[2:]
                    history_key = (board.turn, move)
                    self.history[history_key] = min(100_000, self.history.get(history_key, 0) + depth * depth)
                break

        if best_move is None:
            return 0
        flag = 2 if best_score <= original_alpha else (1 if best_score >= beta else 0)
        if len(self.tt) > 250_000:
            self.tt.clear()
        self.tt[key] = (depth, score_to_tt(best_score, ply), flag, best_move)
        return best_score

    def search_root(self, board: chess.Board, depth: int) -> tuple[int, chess.Move, list[chess.Move]]:
        alpha, beta = -INF, INF
        best_score = -INF
        best_move = next(iter(board.legal_moves))
        root_key = chess.polyglot.zobrist_hash(board)
        tt_entry = self.tt.get(root_key)
        tt_move = tt_entry[3] if tt_entry else None
        for move in self.ordered_moves(board, 0, tt_move):
            self.check_stop()
            board.push(move)
            try:
                score = -self.negamax(board, depth - 1, -beta, -alpha, 1)
            finally:
                board.pop()
            if score > best_score:
                best_score = score
                best_move = move
                self.pv[0] = [move] + self.pv.get(1, [])
            if score > alpha:
                alpha = score
        self.tt[root_key] = (depth, score_to_tt(best_score, 0), 0, best_move)
        return best_score, best_move, self.pv.get(0, [best_move])

    def run(self, board: chess.Board, limits: SearchLimits) -> chess.Move:
        self.limits = limits
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return chess.Move.null()
        best_move = legal_moves[0]
        started = time.monotonic()
        for depth in range(1, limits.max_depth + 1):
            try:
                self.pv.clear()
                score, candidate, pv = self.search_root(board, depth)
            except SearchStopped:
                break
            best_move = candidate
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


def send(line: str) -> None:
    with _output_lock:
        print(line, flush=True)


def parse_go(tokens: list[str]) -> SearchLimits:
    values: dict[str, int] = {}
    flags = {"infinite", "ponder"}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in flags:
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
    max_nodes = values.get("nodes")
    deadline = None
    if "movetime" in values:
        deadline = time.monotonic() + max(0.01, values["movetime"] / 1000.0)
    elif "infinite" not in values and ("wtime" in values or "btime" in values):
        remaining = values.get("wtime" if _board.turn == chess.WHITE else "btime", 1_000)
        increment = values.get("winc" if _board.turn == chess.WHITE else "binc", 0)
        moves_to_go = max(1, values.get("movestogo", 30))
        allocation_ms = max(10, min(max(10, remaining - 50), remaining / moves_to_go + increment * 0.8))
        deadline = time.monotonic() + allocation_ms / 1000.0
    return SearchLimits(max_depth=max_depth, deadline=deadline, max_nodes=max_nodes)


def stop_search(wait: bool = True) -> None:
    global _worker, _stop_event
    worker = _worker
    event = _stop_event
    if event:
        event.set()
    if wait and worker and worker.is_alive() and worker is not threading.current_thread():
        worker.join()
    if wait:
        _worker = None
        _stop_event = None


def start_search(tokens: list[str]) -> None:
    global _worker, _stop_event
    stop_search()
    limits = parse_go(tokens)
    with _state_lock:
        board = _board.copy(stack=True)
    event = threading.Event()
    _stop_event = event

    def report(depth, score, nodes, elapsed_ms, pv):
        if abs(score) >= MATE_THRESHOLD:
            mate_moves = max(1, (MATE - abs(score) + 1) // 2)
            score_text = f"mate {mate_moves if score > 0 else -mate_moves}"
        else:
            score_text = f"cp {score}"
        nps = nodes * 1000 // elapsed_ms
        pv_text = " ".join(move.uci() for move in pv)
        send(f"info depth {depth} score {score_text} nodes {nodes} nps {nps} time {elapsed_ms} pv {pv_text}".rstrip())

    def work():
        searcher = Searcher(event, report)
        best = searcher.run(board, limits)
        send(f"bestmove {best.uci()}")

    _worker = threading.Thread(target=work, daemon=True)
    _worker.start()


def set_position(tokens: list[str]) -> None:
    global _board
    if len(tokens) < 2:
        return
    try:
        if tokens[1] == "startpos":
            board = chess.Board()
            index = 2
        elif tokens[1] == "fen" and len(tokens) >= 8:
            board = chess.Board(" ".join(tokens[2:8]))
            index = 8
        else:
            return
        if index < len(tokens) and tokens[index] == "moves":
            for uci in tokens[index + 1:]:
                board.push_uci(uci)
        with _state_lock:
            _board = board
    except (ValueError, IndexError):
        send("info string Invalid position command")


def main() -> None:
    global _board
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        command = tokens[0]
        if command == "uci":
            send("id name Chess_Bot Python")
            send("id author maciekglow11-design")
            send("uciok")
        elif command == "isready":
            send("readyok")
        elif command == "ucinewgame":
            stop_search()
        elif command == "position":
            stop_search()
            set_position(tokens)
        elif command == "go":
            start_search(tokens)
        elif command == "stop":
            stop_search()
        elif command == "quit":
            stop_search()
            break
        elif command == "setoption":
            # No tunable UCI options are exposed yet; accept the command safely.
            continue


if __name__ == "__main__":
    main()
