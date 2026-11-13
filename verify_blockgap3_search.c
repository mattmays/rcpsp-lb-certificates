/* verify_blockgap3_search.c — part of the checker verify_blockgap3.py (J1, written 2026-11-02 s7; NOT YET AUDITED).
   verify_blockgap2_search.c with ONE change: when the memo is full, memo_store() clears it (all slots emptied, arena rewound) and goes on,
   instead of stopping with MEMFULL. The memo holds only states already refuted by exhaustive search, so clearing it loses information
   (those states are searched again if met again: more nodes) but adds none: every REFUTED is still an exhaustive refutation. Until the
   first clear the search is identical to verify_blockgap2_search.c (same nodes, same states). The RESULT line gains resets=R.
   Original header follows.
   verify_blockgap2_search.c — part of the checker verify_blockgap2.py (J1, written 2026-10-26 s5; NOT YET AUDITED).
   The exhaustive layout search of verify_blockgap.py (its function layout(), rules (4)-(6)) in C, in the same order, with an EXACT memo:
   failed states are stored as full byte keys (rem, P, Dn, b, running) in an arena and compared byte for byte, so a hit is never a
   collision. A state found to admit a layout ends the whole search (as in the Python, where True propagates up at once), so only failed
   states need storing. Node counting matches the Python: one node per non-memoised call.
   stdin:  m nq K
           D budget0 cap arena_mb slots_log2 maxdepth
           C[0..K-1]
           m lines: w dur dem[0..K-1]            (members of R in increasing activity id; w = y * D exactly, budget0 = s * D)
           m lines: m chars '0'/'1'              (compatible(a, b) of verify_blockgap.py, among members)
           m lines: nrw hex words                (Rpred: members preceding the member, bit = member index)
           m lines: nqw hex words                (qpred: Q-predecessors, bit = index in sorted Q)
           m lines: nqw hex words                (qsucc_down: union of down(q) over Q-successors q)
   stdout: RESULT REFUTED|LAYOUT|CAP|MEMFULL|DEPTH nodes=N states=S resets=R   (MEMFULL only if the first allocation fails)
   Build: gcc -O2 -std=c99 -o <bin> verify_blockgap2_search.c   (verify_blockgap2.py builds it itself) */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#define MAXM 512
#define MAXK 8
#define MAXW 8
#define MAXRUN 128

static int m, nq, K, nrw, nqw, maxdepth;
static long long D, budget0, cap;
static long long wt[MAXM];
static int du[MAXM], de[MAXM][MAXK], cap_k[MAXK];
static unsigned char cm[MAXM][MAXM];
static uint64_t rpred[MAXM][MAXW], qpred[MAXM][MAXW], qsd[MAXM][MAXW];

static unsigned char *arena; static size_t arena_size, arena_top = 8;   /* offset 0 means "empty slot" */
static uint64_t *slot; static uint64_t slot_mask, slot_limit, nstored = 0;
static long long nodes = 0;
static int stop = 0;      /* 1 node cap, 2 memo full, 3 depth */

static unsigned char kbuf[4096];
static int key_len(int nrun) { return 8 * nrw + 16 * nqw + 8 + 2 + 3 * nrun; }
static void make_key(const uint64_t *rem, const uint64_t *P, const uint64_t *Dn, long long b, int nrun, const int *ri, const int *rk) {
    unsigned char *p = kbuf;
    memcpy(p, rem, 8 * nrw); p += 8 * nrw;
    memcpy(p, P, 8 * nqw); p += 8 * nqw;
    memcpy(p, Dn, 8 * nqw); p += 8 * nqw;
    memcpy(p, &b, 8); p += 8;
    p[0] = (unsigned char)(nrun & 255); p[1] = (unsigned char)(nrun >> 8); p += 2;
    for (int i = 0; i < nrun; i++) { p[0] = (unsigned char)(ri[i] & 255); p[1] = (unsigned char)(ri[i] >> 8); p[2] = (unsigned char)rk[i]; p += 3; }
}
static uint64_t hash_bytes(const unsigned char *p, int n) {
    uint64_t h = 1469598103934665603ULL;
    for (int i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ULL; }
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 33;
    return h;
}
/* returns 1 if the key in kbuf (length n) is stored */
static int memo_find(int n, uint64_t h) {
    uint64_t i = h & slot_mask;
    for (;;) {
        uint64_t off = slot[i];
        if (off == 0) return 0;
        unsigned int len = arena[off] | ((unsigned int)arena[off + 1] << 8);
        if ((int)len == n && memcmp(arena + off + 2, kbuf, n) == 0) return 1;
        i = (i + 1) & slot_mask;
    }
}
static long long nresets = 0;
static void memo_store(int n, uint64_t h) {
    if (nstored >= slot_limit || arena_top + 2 + (size_t)n > arena_size) {      /* v3: full -> clear everything, then store */
        memset(slot, 0, (size_t)(slot_mask + 1) * sizeof(uint64_t));
        arena_top = 8; nstored = 0; nresets++;
        if (arena_top + 2 + (size_t)n > arena_size) { stop = 2; return; }     /* key longer than the whole arena: cannot happen */
    }
    uint64_t i = h & slot_mask;
    while (slot[i] != 0) i = (i + 1) & slot_mask;
    arena[arena_top] = (unsigned char)(n & 255); arena[arena_top + 1] = (unsigned char)(n >> 8);
    memcpy(arena + arena_top + 2, kbuf, n);
    slot[i] = arena_top; arena_top += 2 + (size_t)n; nstored++;
}

typedef struct {
    int cand[MAXM], nc;             /* candidates, increasing index */
    int ch[MAXM], nch;              /* chosen so far */
    int cur[MAXRUN], curk[MAXRUN], ncur;
    long long lo, hi, b;
    int nonempty;
    int rs[MAXK];                   /* resource sums of cur + chosen */
    uint64_t rem[MAXW], P[MAXW], Dn[MAXW];
} frame;
static frame *fr;

static int layout(int depth, const uint64_t *rem, int nrun, const int *ri, const int *rk, long long b, const uint64_t *P, const uint64_t *Dn);

static int leaf(int depth, long long tot) {
    frame *f = &fr[depth];
    uint64_t P2[MAXW], D2[MAXW];
    for (int t = 0; t < nqw; t++) { P2[t] = f->P[t]; D2[t] = f->Dn[t]; }
    for (int x = 0; x < f->nch; x++) { int j = f->ch[x]; for (int t = 0; t < nqw; t++) { P2[t] |= qpred[j][t]; D2[t] |= qsd[j][t]; } }
    for (int t = 0; t < nqw; t++) if (P2[t] & D2[t]) return 0;          /* rule (6): no such block */
    uint64_t rem2[MAXW]; for (int t = 0; t < nrw; t++) rem2[t] = f->rem[t];
    int ri2[MAXRUN], rk2[MAXRUN], n2 = 0, a = 0, c = 0;
    while (a < f->ncur || c < f->nch) {                                  /* sorted merge by member index */
        if (n2 >= MAXRUN) { fprintf(stderr, "too many running\n"); exit(4); }
        if (c >= f->nch || (a < f->ncur && f->cur[a] < f->ch[c])) { ri2[n2] = f->cur[a]; rk2[n2] = f->curk[a]; a++; }
        else { int j = f->ch[c++]; ri2[n2] = j; rk2[n2] = du[j]; rem2[j >> 6] &= ~(1ULL << (j & 63)); }
        n2++;
    }
    return layout(depth + 1, rem2, n2, ri2, rk2, f->b - (D - tot), P2, D2);
}

static int subsets(int depth, int i, long long tot) {
    frame *f = &fr[depth];
    if (stop) return -1;
    if (i == f->nc) {
        if (tot < f->lo || tot > f->hi) return 0;
        if (f->nonempty && f->nch == 0) return 0;
        return leaf(depth, tot);
    }
    int j = f->cand[i];
    if (tot + wt[j] <= f->hi) {
        int ok = 1;
        for (int x = 0; x < f->nch; x++) if (!cm[j][f->ch[x]]) { ok = 0; break; }
        if (ok) for (int k = 0; k < K; k++) if (f->rs[k] + de[j][k] > cap_k[k]) { ok = 0; break; }
        if (ok) {
            f->ch[f->nch++] = j; for (int k = 0; k < K; k++) f->rs[k] += de[j][k];
            int r = subsets(depth, i + 1, tot + wt[j]);
            f->nch--; for (int k = 0; k < K; k++) f->rs[k] -= de[j][k];
            if (r) return r;
        }
    }
    return subsets(depth, i + 1, tot);
}

static int layout(int depth, const uint64_t *rem, int nrun, const int *ri, const int *rk, long long b, const uint64_t *P, const uint64_t *Dn) {
    if (depth >= maxdepth) { stop = 3; return -1; }
    int n = key_len(nrun);
    make_key(rem, P, Dn, b, nrun, ri, rk);
    uint64_t h = hash_bytes(kbuf, n);
    if (memo_find(n, h)) return 0;
    nodes++;
    if (nodes > cap) { stop = 1; return -1; }
    frame *f = &fr[depth];
    int r;
    if (nrun == 0) {
        int empty = 1; for (int t = 0; t < nrw; t++) if (rem[t]) { empty = 0; break; }
        if (empty) return 1;
        f->ncur = 0; f->nch = 0; f->lo = D - b; f->hi = D; f->b = b; f->nonempty = 1;
        for (int t = 0; t < nrw; t++) f->rem[t] = rem[t];
        for (int t = 0; t < nqw; t++) { f->P[t] = 0; f->Dn[t] = 0; }
        for (int k = 0; k < K; k++) f->rs[k] = 0;
        f->nc = 0;
        for (int j = 0; j < m; j++) {
            if (!((rem[j >> 6] >> (j & 63)) & 1)) continue;
            if (wt[j] > f->hi) continue;
            int ok = 1;
            for (int k = 0; k < K; k++) if (de[j][k] > cap_k[k]) { ok = 0; break; }
            for (int t = 0; ok && t < nrw; t++) if (rpred[j][t] & rem[t]) ok = 0;      /* rule (5): unfinished = rem */
            if (ok) f->cand[f->nc++] = j;
        }
        r = subsets(depth, 0, 0);
    } else {
        int nk[MAXRUN], nkk[MAXRUN], nn = 0;
        for (int i = 0; i < nrun; i++) if (rk[i] > 1) { nk[nn] = ri[i]; nkk[nn] = rk[i] - 1; nn++; }
        if (nn == 0) {
            uint64_t z[MAXW]; memset(z, 0, sizeof z);
            r = layout(depth + 1, rem, 0, nk, nkk, b, z, z);                 /* the block may end; fresh rule (6) state */
        } else {
            long long wc = 0;
            f->ncur = nn; f->nch = 0; f->lo = D - b; f->hi = D; f->b = b; f->nonempty = 0;
            for (int k = 0; k < K; k++) f->rs[k] = 0;
            for (int i = 0; i < nn; i++) { f->cur[i] = nk[i]; f->curk[i] = nkk[i]; wc += wt[nk[i]]; for (int k = 0; k < K; k++) f->rs[k] += de[nk[i]][k]; }
            for (int t = 0; t < nrw; t++) f->rem[t] = rem[t];
            for (int t = 0; t < nqw; t++) { f->P[t] = P[t]; f->Dn[t] = Dn[t]; }
            uint64_t unf[MAXW]; for (int t = 0; t < nrw; t++) unf[t] = rem[t];
            for (int i = 0; i < nn; i++) unf[nk[i] >> 6] |= 1ULL << (nk[i] & 63);
            f->nc = 0;
            for (int j = 0; j < m; j++) {
                if (!((rem[j >> 6] >> (j & 63)) & 1)) continue;
                if (wc + wt[j] > f->hi) continue;
                int ok = 1;
                for (int i = 0; i < nn; i++) if (!cm[j][nk[i]]) { ok = 0; break; }
                for (int k = 0; ok && k < K; k++) if (f->rs[k] + de[j][k] > cap_k[k]) ok = 0;
                for (int t = 0; ok && t < nrw; t++) if (rpred[j][t] & unf[t]) ok = 0;   /* rule (5): unfinished = rem + running */
                if (ok) f->cand[f->nc++] = j;
            }
            r = subsets(depth, 0, wc);
        }
    }
    if (r == 0 && !stop) {
        make_key(rem, P, Dn, b, nrun, ri, rk);    /* kbuf was overwritten by deeper calls */
        memo_store(n, h);
    }
    return r;
}

int main(void) {
    long long arena_mb; int slots_log2;
    if (scanf("%d %d %d", &m, &nq, &K) != 3) return 2;
    if (scanf("%lld %lld %lld %lld %d %d", &D, &budget0, &cap, &arena_mb, &slots_log2, &maxdepth) != 6) return 2;
    if (m < 1 || m > MAXM || nq < 0 || nq > 64 * MAXW || K < 1 || K > MAXK || slots_log2 < 10 || slots_log2 > 34) { fprintf(stderr, "bad sizes\n"); return 2; }
    nrw = (m + 63) / 64; nqw = (nq + 63) / 64;
    for (int k = 0; k < K; k++) if (scanf("%d", &cap_k[k]) != 1) return 2;
    for (int j = 0; j < m; j++) {
        if (scanf("%lld %d", &wt[j], &du[j]) != 2) return 2;
        if (du[j] < 1 || du[j] > 255 || wt[j] < 1 || wt[j] > D) { fprintf(stderr, "bad member data\n"); return 2; }
        for (int k = 0; k < K; k++) if (scanf("%d", &de[j][k]) != 1) return 2;
    }
    char row[MAXM + 8];
    for (int j = 0; j < m; j++) {
        if (scanf("%s", row) != 1 || (int)strlen(row) != m) { fprintf(stderr, "bad compat row\n"); return 2; }
        for (int x = 0; x < m; x++) cm[j][x] = row[x] == '1';
    }
    for (int j = 0; j < m; j++) for (int t = 0; t < nrw; t++) { unsigned long long v; if (scanf("%llx", &v) != 1) return 2; rpred[j][t] = v; }
    for (int j = 0; j < m; j++) for (int t = 0; t < nqw; t++) { unsigned long long v; if (scanf("%llx", &v) != 1) return 2; qpred[j][t] = v; }
    for (int j = 0; j < m; j++) for (int t = 0; t < nqw; t++) { unsigned long long v; if (scanf("%llx", &v) != 1) return 2; qsd[j][t] = v; }
    arena_size = (size_t)arena_mb << 20;
    arena = malloc(arena_size);
    uint64_t ns = 1ULL << slots_log2; slot_mask = ns - 1; slot_limit = (ns / 10) * 7;
    slot = calloc(ns, sizeof(uint64_t));
    fr = calloc((size_t)maxdepth + 2, sizeof(frame));
    if (!arena || !slot || !fr) { printf("RESULT MEMFULL nodes=0 states=0 resets=0\n"); return 0; }
    uint64_t rem[MAXW] = {0}, z[MAXW] = {0};
    for (int j = 0; j < m; j++) rem[j >> 6] |= 1ULL << (j & 63);
    int ri[1], rk[1];
    int r = layout(0, rem, 0, ri, rk, budget0, z, z);
    const char *v = stop == 1 ? "CAP" : stop == 2 ? "MEMFULL" : stop == 3 ? "DEPTH" : r == 1 ? "LAYOUT" : "REFUTED";
    printf("RESULT %s nodes=%lld states=%llu resets=%lld\n", v, nodes, (unsigned long long)nstored, nresets);
    return 0;
}
