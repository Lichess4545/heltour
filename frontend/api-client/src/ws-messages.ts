import { z } from "zod";

// Mirror of `MatchDTO` in `heltour/api/schemas.py`. Hand-written rather
// than reused from `generated.ts` so the WS payload shape is checked at
// runtime — generated types from openapi-typescript aren't zod schemas.
const matchDto = z.object({
  id: z.number().int(),
  white_username: z.string().nullable(),
  black_username: z.string().nullable(),
  white_fide_name: z.string().nullable(),
  black_fide_name: z.string().nullable(),
  white_rating: z.number().int().nullable(),
  black_rating: z.number().int().nullable(),
  white_gender: z.string().nullable(),
  black_gender: z.string().nullable(),
  white_is_captain: z.boolean(),
  black_is_captain: z.boolean(),
  result: z.string(),
  game_link: z.string(),
  board_number: z.number().int().nullable(),
  team_match_id: z.number().int().nullable(),
});

const teamMatchDto = z.object({
  id: z.number().int(),
  pairing_order: z.number().int(),
  white_team_name: z.string(),
  white_team_number: z.number().int(),
  black_team_name: z.string().nullable(),
  black_team_number: z.number().int().nullable(),
  white_score: z.number(),
  black_score: z.number(),
  is_bye: z.boolean(),
});

export const wsMatchUpdate = z.object({
  type: z.literal("match.update"),
  round_id: z.number().int(),
  match: matchDto,
});

export const wsTeamMatchUpdate = z.object({
  type: z.literal("team_match.update"),
  round_id: z.number().int(),
  team_match: teamMatchDto,
});

export const wsPing = z.object({ type: z.literal("ping") });

export const wsMessage = z.discriminatedUnion("type", [wsMatchUpdate, wsTeamMatchUpdate, wsPing]);

export type WSMatchUpdate = z.infer<typeof wsMatchUpdate>;
export type WSTeamMatchUpdate = z.infer<typeof wsTeamMatchUpdate>;
export type WSPing = z.infer<typeof wsPing>;
export type WSMessage = z.infer<typeof wsMessage>;
