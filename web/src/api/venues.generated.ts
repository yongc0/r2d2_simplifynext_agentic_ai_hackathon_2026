/**
 * GENERATED FILE — do not edit by hand.
 *
 * Written by `spark/scripts/export_venues_for_web.py` from
 * `spark/data/venues_osm.json`, which `spark/scripts/fetch_venues.py` fetches
 * once from OpenStreetMap.
 *
 * It is generated rather than hand-written for one reason: nobody can
 * accidentally type a plausible address into a generated file. Every venue here
 * is a real place somebody contributed to OpenStreetMap, and Spark has visited
 * and evaluated none of them.
 *
 * THE LIST BELOW IS EMPTY UNTIL THOSE TWO SCRIPTS HAVE RUN, and empty is a
 * legitimate state: the offline demo then shows "we cannot name places yet"
 * rather than inventing somewhere to go.
 *
 *   cd spark
 *   uv run python scripts/fetch_venues.py
 *   uv run python scripts/export_venues_for_web.py
 *
 * Licence: any surface rendering these venues must show
 * "© OpenStreetMap contributors".
 */

export interface MockVenue {
  venueId: string;
  name: string;
  category: "activity" | "food" | "drink";
  budget: string;
  energy: string;
  lat: number;
  lon: number;
  /** `null` when OpenStreetMap has no address for it. Never a guess. */
  address: string | null;
  /** `null` means UNKNOWN. It must never be rendered as "open". */
  openingHours: string | null;
  interests: string[];
}

export const GENERATED_VENUES: MockVenue[] = [
  {
    "venueId": "osm-n10036347310",
    "name": "Dennis Gym",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.322851,
    "lon": 103.852095,
    "address": "279 Balestier Road, 329727",
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n10808393883",
    "name": "Ellie Art Studio",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.333951,
    "lon": 103.888016,
    "address": "601 MacPherson Road, 368242",
    "openingHours": "Mo-Su 11:30-21:00",
    "interests": [
      "photography",
      "film"
    ]
  },
  {
    "venueId": "osm-n10980076782",
    "name": "bommoi",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.279456,
    "lon": 103.842435,
    "address": "61A Neil rd, 088895",
    "openingHours": "We-Su 11:00-19:00",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n8482680637",
    "name": "Kallang park connector",
    "category": "activity",
    "budget": "free",
    "energy": "medium",
    "lat": 1.320888,
    "lon": 103.867166,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "running",
      "cycling",
      "birdwatching",
      "gardening"
    ]
  },
  {
    "venueId": "osm-n10287172753",
    "name": "Anytime Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.326718,
    "lon": 103.845965,
    "address": "520 Balestier Road, 329853",
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n10808393880",
    "name": "Anytime Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.333681,
    "lon": 103.887641,
    "address": "601 MacPherson Road, 368242",
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n11017124122",
    "name": "Homeground Gym",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.314536,
    "lon": 103.852532,
    "address": "146 Owen Road, 218943",
    "openingHours": "Mo-Fr 12:00-20:00; Sa 00:30-14:30; Su,PH off",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n11090494252",
    "name": "Anytime Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.292264,
    "lon": 103.85443,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n11345784271",
    "name": "GoFit-X Geylang",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.311897,
    "lon": 103.880498,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n11391788425",
    "name": "Art Works Gallery",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.31117,
    "lon": 103.793813,
    "address": "7 Holland Village Way, 275748",
    "openingHours": "Mo-Su 12:00-20:00",
    "interests": [
      "photography",
      "film"
    ]
  },
  {
    "venueId": "osm-n11408710036",
    "name": "Anytime Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.297262,
    "lon": 103.85525,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n11472827655",
    "name": "Book Bar",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.278043,
    "lon": 103.843232,
    "address": "57 Duxton Road, 089521",
    "openingHours": "Mo-Th 09:30-19:00; Fr-Sa 09:30-22:00; Su 09:30-18:00",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n11627229964",
    "name": "Eagle’s Eye Gallery",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.286936,
    "lon": 103.847211,
    "address": "34B North Canal Road, 059290",
    "openingHours": "We-Sa 10:00-18:30",
    "interests": [
      "photography",
      "film"
    ]
  },
  {
    "venueId": "osm-n12533886465",
    "name": "Books Without Borders",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.281114,
    "lon": 103.845212,
    "address": "33 Erskine Road",
    "openingHours": "11:00-20:00",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n12533886471",
    "name": "Du Yi Bookshop",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.321141,
    "lon": 103.846044,
    "address": null,
    "openingHours": "08:30-20:30",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n3068355885",
    "name": "Books Kinokuniya Bugis Junction Store",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.299605,
    "lon": 103.855485,
    "address": "200 Victoria Street, 188021",
    "openingHours": "Mo-Su 11:00-21:00",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n3561043147",
    "name": "Kinokuniya",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.303138,
    "lon": 103.834038,
    "address": "391 Orchard Road, 238872",
    "openingHours": "Mo-Su 10:00-21:30",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n4631657928",
    "name": "MoveToLive",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.301929,
    "lon": 103.79386,
    "address": "8A Biomedical Grove, 138648",
    "openingHours": "08:00-21:00",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n4733059561",
    "name": "SG Pho House",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.303522,
    "lon": 103.859826,
    "address": "North Bridge Road, 198742",
    "openingHours": "Mo-Su 10:00-22:00",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n4738733376",
    "name": "Anytime Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.284221,
    "lon": 103.846003,
    "address": "South Bridge Road",
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n4749101762",
    "name": "Zee Fitness",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.326904,
    "lon": 103.844579,
    "address": "560A Balestier Road, 329876",
    "openingHours": "24/7",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n4990159421",
    "name": "Fitness First Market Street",
    "category": "activity",
    "budget": "under_20",
    "energy": "high",
    "lat": 1.283854,
    "lon": 103.850494,
    "address": null,
    "openingHours": "Mo-Fr 06:00-22:00; Sa 07:00-17:00; Su 08:00-16:00",
    "interests": [
      "running",
      "swimming",
      "yoga"
    ]
  },
  {
    "venueId": "osm-n5110704825",
    "name": "Wardah Books",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.301666,
    "lon": 103.85951,
    "address": "58 Bussorah Street, 199474",
    "openingHours": "Mo-Fr 10:00-20:00; Sa-Su 09:00-20:00",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n5760025047",
    "name": "NUS Co-op",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.319013,
    "lon": 103.816771,
    "address": "469 Bukit Timah Road, 259756",
    "openingHours": "Mo-We, Fr 10:00-17:00; Th 10:00-19:00; Sa,Su,PH off",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n5924056474",
    "name": "Popular",
    "category": "activity",
    "budget": "free",
    "energy": "low",
    "lat": 1.286406,
    "lon": 103.826681,
    "address": null,
    "openingHours": "Mo-Fr 11:00-21:00; PH,Sa-Su 10:30-21:30",
    "interests": [
      "reading",
      "languages"
    ]
  },
  {
    "venueId": "osm-n12136676397",
    "name": "Tekka Wet Market",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.306521,
    "lon": 103.850483,
    "address": "665 Buffalo Road, 210665",
    "openingHours": "06:30-17:00",
    "interests": [
      "cooking",
      "baking"
    ]
  },
  {
    "venueId": "osm-n1318605429",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.274883,
    "lon": 103.846034,
    "address": null,
    "openingHours": "Mo-Su 07:00-00:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1572429498",
    "name": "No Signboard Seafood Restaurant",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.289084,
    "lon": 103.855677,
    "address": "8，#01-14",
    "openingHours": "Mo-Su 11:00-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1725462475",
    "name": "Thai Royal Cuisine",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.334556,
    "lon": 103.809949,
    "address": "251 Arcadia Road, 289848",
    "openingHours": "Mo-Fr 12:00-15:00,16:30-22:00; Sa-Su,PH 11:30-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1829431135",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.284543,
    "lon": 103.842675,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1829455634",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.304542,
    "lon": 103.833552,
    "address": null,
    "openingHours": "Mo-Su 07:00-23:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1832093563",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.282813,
    "lon": 103.865391,
    "address": null,
    "openingHours": "Mo-Su 08:30-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1832093665",
    "name": "Marguerite",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.284864,
    "lon": 103.864031,
    "address": "18 Marina Gardens Drive, 018953",
    "openingHours": "We-Su 18:00-22:00; Fr-Su 12:00-15:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1837344951",
    "name": "Yum Cha Chinatown",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.282919,
    "lon": 103.843917,
    "address": "20 Trengganu Street, 058479",
    "openingHours": "Mo-Fr 10:30-22:30; Sa,Su 09:00-22:30",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1951506309",
    "name": "Hard Rock Cafe",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.305887,
    "lon": 103.828177,
    "address": "50 Cuscaden Road, 249724",
    "openingHours": "Mo-Th 11:30-00:00; Fr-Su 11:30-02:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1953018711",
    "name": "Burger King",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.289064,
    "lon": 103.846966,
    "address": null,
    "openingHours": "Su-Th 08:00-23:00;Fr-Sa 08:00-02:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1953018713",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.306334,
    "lon": 103.828724,
    "address": null,
    "openingHours": "24/7",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2022346771",
    "name": "Gerry's Grill",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.302835,
    "lon": 103.840585,
    "address": "57 Cuppage Road",
    "openingHours": "Tu-Sa 12:00-22:30; Su 11:30-22:30",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2099138260",
    "name": "Long Beach @ Robertson Quay",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.289674,
    "lon": 103.839116,
    "address": "60 Robertson Quay, 238252",
    "openingHours": "Mo-Th,Su,PH 11:00-23:00; Fr-Sa 11:00-23:30",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2099138267",
    "name": "Kingdom of Belgians - KOB",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.289868,
    "lon": 103.8375,
    "address": "8 Rodyk Street, 238216",
    "openingHours": "Tu-Th 14:00-23:00; Fr-Su 11:30-23:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2132500347",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.320475,
    "lon": 103.885784,
    "address": "Ajunied Avenue 2",
    "openingHours": "24/7",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2231822574",
    "name": "Jaan",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.293166,
    "lon": 103.853301,
    "address": "2 Seah Street",
    "openingHours": "Mo-Sa 12:00-14:30, 19:00-22:30",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402528907",
    "name": "Casa Vostra",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.293225,
    "lon": 103.853234,
    "address": "252 #01-49/50/51 North Bridge Road, 179103",
    "openingHours": "Mo-Su 11:30-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402530866",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.28584,
    "lon": 103.849966,
    "address": "1 South Canal Road, 048508",
    "openingHours": "24/7",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402536811",
    "name": "Burger King",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.30074,
    "lon": 103.844785,
    "address": null,
    "openingHours": "Su-Th 08:30-22:30; Fr-Sa 08:30-23:30",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402536816",
    "name": "McDonald's",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.300011,
    "lon": 103.84489,
    "address": null,
    "openingHours": "Mo-Su 07:30-23:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402536817",
    "name": "MOS Burger",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.300143,
    "lon": 103.844557,
    "address": null,
    "openingHours": "Su-Th 10:00-22:30; Fr-Sa 10:00-23:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2402536818",
    "name": "Tim Ho Wan",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.299817,
    "lon": 103.845253,
    "address": "68 Orchard Road, 238839",
    "openingHours": "Mo-Fr 10:00-22:00, Sa-Su 09:00-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2502377892",
    "name": "Ramen Keisuke Tonkotsu King Four Season",
    "category": "food",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.300983,
    "lon": 103.855335,
    "address": null,
    "openingHours": "Mo-Fr 11:30-14:30,17:00-22:30; Sa-Su 11:30-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n2767277547",
    "name": "Subway",
    "category": "food",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.327046,
    "lon": 103.846316,
    "address": "20 Ah Hood Road",
    "openingHours": "08:00-22:00",
    "interests": [
      "cooking"
    ]
  },
  {
    "venueId": "osm-n1275482845",
    "name": "Starbucks",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.306454,
    "lon": 103.832416,
    "address": "9 Scotts Road, 228210",
    "openingHours": "24/7",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n1766486405",
    "name": "Long Bar",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.295131,
    "lon": 103.853468,
    "address": "1 Beach Road, 189673",
    "openingHours": "Su-Th 11:00-00:30; Fr-Sa 11:00-01:30",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n1950182530",
    "name": "Nanyang Old Coffee",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.281809,
    "lon": 103.844895,
    "address": "268 South Bridge Road, 058817",
    "openingHours": "Mo-Su 07:00-21:45",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n2099138257",
    "name": "Toby's Estate",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.289934,
    "lon": 103.837401,
    "address": "8 Rodyk Street, 238216",
    "openingHours": "Mo-Th,Su 07:30-18:00; Fr,Sa 07:30-19:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n2099138258",
    "name": "Botany",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.290063,
    "lon": 103.837202,
    "address": "86 Robertson Quay, 238245",
    "openingHours": "Mo-Fr 09:00-22:00; Sa,Su,PH 08:30-22:00",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n2099138259",
    "name": "Boomarang Bistro & Bar",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.289599,
    "lon": 103.838777,
    "address": "60 Robertson Quay, 238252",
    "openingHours": "06:00-03:00",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n2231979054",
    "name": "1-Altitude Rooftop Gallery & Bar",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.284741,
    "lon": 103.851097,
    "address": "1 Raffles Place, 048616",
    "openingHours": "Su-Tu 18:00-02:00, Th 18:00-03:00, We,Fr,Sa 18:00-04:00",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n2614471363",
    "name": "The Rooftop",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.287036,
    "lon": 103.853537,
    "address": null,
    "openingHours": "17:00-24:00; Sa,Su 17:00-02:00; Su off",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n3307075245",
    "name": "Starbucks",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.288739,
    "lon": 103.846844,
    "address": "Eu Tong Sen Street, 059817",
    "openingHours": "Su-Th 07:30-24:00, Fr-Sa",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3336359310",
    "name": "The Audacious Cakery",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.277417,
    "lon": 103.839582,
    "address": "2 Everton Park, 081002",
    "openingHours": "Tu-Sa 10:00-19:00; Su 10:00-17:00; Mo off",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3337198922",
    "name": "Toast Box",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.308128,
    "lon": 103.862232,
    "address": "French Road, 200809",
    "openingHours": "07:30-22:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3369782863",
    "name": "The Reading Room",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.279019,
    "lon": 103.840549,
    "address": "19 Bukit Pasoh Road, 089833",
    "openingHours": "11:00-23:30",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3670497548",
    "name": "Starbucks",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.301525,
    "lon": 103.856912,
    "address": "585 North Bridge Road, 188770",
    "openingHours": "Mo-Fr 07:30-20:00; Sa-Su,PH 08:00-20:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3759784409",
    "name": "5 The Moments Cafe",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.278066,
    "lon": 103.843814,
    "address": "73 Tanjong Pagar Road, 088494",
    "openingHours": "Su-Th 12:00-23:00; Fr,Sa 12:00-23:30",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3759819048",
    "name": "Yuen Yeung",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.279764,
    "lon": 103.842797,
    "address": "43 Neil Road, 088825",
    "openingHours": "11:00-23:30",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3759828395",
    "name": "fieldnotes",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.279782,
    "lon": 103.842844,
    "address": "41 Neil Road, 088824",
    "openingHours": "Su-Th 11:30-09:00; Fr-Sa 11:00-23:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3789175693",
    "name": "KOI Thé",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.307216,
    "lon": 103.790122,
    "address": "#01-02/03, 100 North Buona Vista Road, 139345",
    "openingHours": "11:00-22:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3816468971",
    "name": "Boulevard",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.280137,
    "lon": 103.854391,
    "address": "Marina Boulevard, 018981",
    "openingHours": "09:00-24:00, Sa closed, Su closed",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n3828352882",
    "name": "Baker And Cook",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.311564,
    "lon": 103.796654,
    "address": "44 Jalan Merah Saga, 278116",
    "openingHours": "Mo-Su 07:30-19:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3964413091",
    "name": "La Champañeria",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.27847,
    "lon": 103.842624,
    "address": "21 Duxton Hill, 089604",
    "openingHours": "Mo-Sa 17:00-24:00",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n3987259010",
    "name": "Gink-Go",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.342473,
    "lon": 103.834908,
    "address": null,
    "openingHours": "Mo-Tu,Sa-Su,PH off; We-Th 07:30-12:30; Fr 07:30-19:30",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n3987288993",
    "name": "Habitat Coffee",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.352783,
    "lon": 103.834509,
    "address": "223 Upper Thomson Road, 574355",
    "openingHours": "Tu-Su 10:00-22:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n4030843894",
    "name": "Le bar / Taste",
    "category": "drink",
    "budget": "under_50",
    "energy": "low",
    "lat": 1.301087,
    "lon": 103.852456,
    "address": null,
    "openingHours": "Mo-Su 06:00-22:00",
    "interests": [
      "live music"
    ]
  },
  {
    "venueId": "osm-n4066561924",
    "name": "(Working Title)",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.30292,
    "lon": 103.851956,
    "address": "1 McNally Street, 187940",
    "openingHours": "Mo-Sa 09:30-22:00; Su 09:00-15:00",
    "interests": [
      "coffee",
      "reading"
    ]
  },
  {
    "venueId": "osm-n4146903387",
    "name": "Mahmud’s Tandoor",
    "category": "drink",
    "budget": "under_20",
    "energy": "low",
    "lat": 1.302335,
    "lon": 103.859604,
    "address": "20 Kandahar Street, 198885",
    "openingHours": "Mo off; Tu-Su 11:30-21:00",
    "interests": [
      "coffee",
      "reading"
    ]
  }
];

/** Written by the export script so the interface can say how fresh this is. */
export const GENERATED_AT: string | null = "2026-09-02";
