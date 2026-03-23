#!/usr/bin/env python3
"""
SSA consultative sales crystal injection script.
Source: Consultative Sales Crystal Cluster (345 pages, 67 crystals)
67 crystals = 30 PRI + 25 PAT + 12 LES
"""
import json
from datetime import datetime

CRYSTALS_PATH = "/Users/ZEALCHOU/MUSEON/data/lattice/crystals.json"
NOW = datetime.now().isoformat()


def make_crystal(
    cuid, crystal_type, g1, g2, g3, g4, assumption, evidence, tags,
    skill_affinity=None,
    limitation="applicable to consultative sales contexts",
):
    return {
        "cuid": cuid,
        "crystal_type": crystal_type,
        "g1_summary": g1,
        "g2_structure": g2,
        "g3_root_inquiry": g3,
        "g4_insights": g4,
        "assumption": assumption,
        "evidence": evidence,
        "limitation": limitation,
        "verification_level": "validated",
        "created_at": NOW,
        "updated_at": NOW,
        "archived": False,
        "ri_score": 0.75,
        "reference_count": 0,
        "last_referenced": NOW,
        "domain": "OneMuse",
        "success_count": 0,
        "counter_evidence_count": 0,
        "source_context": "OneMuse/SSA/consultative-sales-crystal-cluster",
        "status": "active",
        "origin": "SSA-consultative-sales-crystal-cluster-345pages",
        "skill_affinity": skill_affinity or ["ssa-consultant"],
        "tags": tags,
    }


def build_principles():
    ps = []
    # CH1 (3)
    ps.append(make_crystal(
        "KL-PRI-0280", "Principle",
        "consultative sales essence: finding answers together, not pushing products",
        "Consultative sales != pushing. Core shift: from 'I have something to sell you' to 'let us see what fits you best'. The seller's role transforms from pusher to co-explorer.",
        "What is the true nature of selling?",
        ["The biggest enemy of sales is not rejection but the customer feeling pushed",
         "The posture of co-exploration is itself the strongest persuasion",
         "Consultative selling redefines the power structure of buyer-seller relationships"],
        "Customers have intrinsic motivation to find answers; they just need guidance",
        "Source: Consultative Sales Crystal Cluster CH1 C1-01",
        ["consultative-sales", "sales-essence", "co-creation", "push-vs-consult"]))

    ps.append(make_crystal(
        "KL-PRI-0281", "Principle",
        "Transaction is the result; empathy is the prerequisite -- no empathy, no close",
        "Causal chain: empathy -> trust -> real needs surface -> precise solution -> natural close. Empathy is not a technique but an attitude. It is the key that opens the customer's heart, not a tool to shut the door.",
        "What is the true precondition for closing a deal?",
        ["Rushing to close actually closes the possibility of closing",
         "Empathy shifts the customer from defensive to open",
         "The transaction is merely the natural extension of empathy"],
        "People are more willing to commit when they feel understood",
        "Source: Consultative Sales Crystal Cluster CH1 C1-02",
        ["empathy", "closing-prerequisite", "trust-building", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0282", "Principle",
        "A good salesperson is like a doctor: asking is more important than talking",
        "Doctor model: Observe -> Listen -> Ask -> Diagnose -> Prescribe. A salesperson should spend 80% of time listening and asking, 20% talking. Diagnose before prescribing; reversing the order is malpractice.",
        "Is the core competency of a salesperson persuasion or questioning?",
        ["The quality of questions determines the quality of sales",
         "A salesperson who talks too much is like a doctor who ignores the patient",
         "Good questions let the customer see the answer themselves"],
        "Customers already have the embryo of an answer inside; it needs activation by good questions",
        "Source: Consultative Sales Crystal Cluster CH1 C1-03",
        ["questioning-power", "doctor-model", "diagnostic-sales", "consultative-sales"]))

    # CH2 (3)
    ps.append(make_crystal(
        "KL-PRI-0283", "Principle",
        "Eight-direction energy (Wind-Water-Mountain-Fire-Heaven-Earth-Lake-Thunder) = spectrum of how customers want to be treated",
        "Eight energies map to eight psychological needs: Wind=relaxed, Water=listened-to, Mountain=organized, Fire=ignited, Heaven=trusted, Earth=stabilized, Lake=connected, Thunder=pushed. Each customer needs different energy at different moments.",
        "What dimensions describe how customers want to be treated?",
        ["Energy is not the seller's weapon but the customer's need",
         "Reading which energy the customer needs right now is the core skill of top salespeople",
         "The eight directions are dynamic -- the same customer needs different energies at different moments"],
        "Human psychological needs can be classified into a finite set of energy patterns",
        "Source: Consultative Sales Crystal Cluster CH2 C2-01",
        ["eight-direction-energy", "customer-psychology", "energy-spectrum", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    ps.append(make_crystal(
        "KL-PRI-0284", "Principle",
        "Using the wrong energy is worse than silence -- misaligned energy poisons the relationship",
        "Misalignment examples: customer needs stabilizing (Earth) but you push (Thunder) -> panic escalates; customer needs listening (Water) but you organize (Mountain) -> feels negated. Damage from misalignment > damage from silence.",
        "Why do some salespeople drive customers away the harder they try?",
        ["Effort in the wrong direction is more dangerous than no effort",
         "Energy misalignment makes the customer feel 'you don't get me'",
         "Silence is sometimes the best energy -- at least it won't misalign"],
        "Most sales failures stem not from insufficient effort but from misdirected energy",
        "Source: Consultative Sales Crystal Cluster CH2 C2-02",
        ["energy-misalignment", "sales-failure", "customer-feeling", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    ps.append(make_crystal(
        "KL-PRI-0285", "Principle",
        "True selling is 'energy switching' -- delivering the right energy at the right moment",
        "Energy-switching ability = sensing the customer's current state + selecting the matching energy + switching instantly. This is not acting; it is genuine perceptual skill. The gap between a master and a novice is not scripts but switching speed and accuracy.",
        "What is the fundamental difference between elite and average salespeople?",
        ["Energy switching is a trainable perceptual ability",
         "Scripts can be learned; energy switching must be practiced",
         "The key to switching is 'receive first, then switch' -- never jump directly"],
        "Selling is a dynamic energy dialogue, not a static information transfer",
        "Source: Consultative Sales Crystal Cluster CH2 C2-03",
        ["energy-switching", "perceptual-skill", "dynamic-sales", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    # CH3 (3)
    ps.append(make_crystal(
        "KL-PRI-0286", "Principle",
        "The first 90 seconds determine how deep the relationship can go",
        "Golden 90-second rule: in the first 90 seconds the customer judges three things -- Is this person safe? Does this person understand me? Is this person worth my time? The impression formed in 90 seconds influences the entire relationship.",
        "When is the depth of a relationship already decided?",
        ["First impressions affect not just the opening but the ceiling of the whole relationship",
         "The judgments customers make in 90 seconds are subconscious and intuitive",
         "Safety is the foundation of all these judgments"],
        "The subconscious makes trust judgments in extremely short timeframes",
        "Source: Consultative Sales Crystal Cluster CH3 C3-01",
        ["golden-90-seconds", "first-impression", "trust-building", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0287", "Principle",
        "True connection is not shared interests but shared problems",
        "Shallow vs deep connection: chatting about hobbies is surface-level and fades over time; facing the same problem together is deep and strengthens with challenge. Finding a shared problem > finding a shared interest.",
        "What kind of connection can sustain a long-term advisory relationship?",
        ["Shared interests make people like you; shared problems make people need you",
         "Deep connection is built on the experience of solving problems together",
         "Shifting from chatting about interests to discussing problems is the turning point of relationship deepening"],
        "The deepest human bonds come from shared experiences of facing challenges",
        "Source: Consultative Sales Crystal Cluster CH3 C3-03",
        ["deep-connection", "shared-problems", "relationship-deepening", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0288", "Principle",
        "The endpoint of relationship building is making the customer willing to reveal their true needs",
        "Purpose indicator of relationship building: the customer moves from polite -> sincere -> vulnerable. When the customer is willing to voice real pain points and concerns rather than just surface needs, the relationship is truly established.",
        "At what point is a relationship 'deep enough'?",
        ["The customer's politeness is a wall, not a door",
         "True needs only surface when safety is sufficient",
         "The relationship is not the goal; it is the condition for real needs to emerge"],
        "People only reveal genuine needs when they feel sufficiently safe",
        "Source: Consultative Sales Crystal Cluster CH3 C3-05",
        ["true-needs", "safety", "relationship-purpose", "consultative-sales"]))

    # CH4 (3)
    ps.append(make_crystal(
        "KL-PRI-0289", "Principle",
        "Needs are not extracted by questions; they surface when the customer feels understood",
        "Need-emergence mechanism: customers don't reveal needs because they're asked the right question -- they reveal needs when they 'feel understood' in the conversation. The purpose of questioning is not information extraction but creating the feeling of being understood.",
        "How do needs actually emerge?",
        ["Asking many questions does not equal asking good questions",
         "Need emergence requires emotional safety as a precondition",
         "Good questioning makes customers surprise themselves with what they say"],
        "Needs are emotion-driven, not logic-driven",
        "Source: Consultative Sales Crystal Cluster CH4 C4-01",
        ["need-emergence", "emotional-safety", "questioning-purpose", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0290", "Principle",
        "The sequence of questions matters more than the questions themselves",
        "Questioning sequence logic: open questions (build safety) -> situation questions (understand status quo) -> pain questions (touch emotions) -> vision questions (see possibilities). Wrong sequence means the same question gets completely different answers.",
        "Why is the same question sometimes effective and sometimes not?",
        ["Asking about pain first is like performing surgery before anesthesia",
         "The sequence itself is a form of communication",
         "A good sequence makes the customer feel guided rather than interrogated"],
        "Psychological openness is progressive and requires the right guidance sequence",
        "Source: Consultative Sales Crystal Cluster CH4 C4-03",
        ["questioning-sequence", "progressive-openness", "guided-dialogue", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0291", "Principle",
        "Safety is the only key that unlocks needs",
        "Three elements of safety: not being judged (nothing I say will be ridiculed), not being sold to (revealing needs won't be exploited), not being rushed (I can think at my own pace). Missing any one element closes the door to needs.",
        "Under what conditions will a customer truly open up?",
        ["Safety is not declared; it is demonstrated",
         "Customers will test whether you are truly safe",
         "Rushing is the greatest enemy of safety"],
        "People reveal true needs and vulnerability only when feeling psychologically safe",
        "Source: Consultative Sales Crystal Cluster CH4 C4-05",
        ["safety", "need-openness", "no-rushing", "consultative-sales"]))

    # CH5 (3)
    ps.append(make_crystal(
        "KL-PRI-0292", "Principle",
        "Pain points have three layers: surface behavior -> emotional connection -> underlying belief",
        "Three-layer pain model: L1 surface behavior (what they did/didn't do) -> L2 emotional connection (how it makes them feel) -> L3 underlying belief (what they believe that causes the pain). Treating only L1 is a band-aid; reaching L3 is real healing.",
        "What is the deep structure of pain points? Why does the same pain lead some to change and others not?",
        ["Most salespeople only touch L1 -- that's why proposals are ignored",
         "L3 underlying belief is the leverage point for change",
         "Guiding from L1 to L3 requires immense trust"],
        "Behavior has emotions behind it; emotions have beliefs behind them",
        "Source: Consultative Sales Crystal Cluster CH5 C5-01",
        ["three-layer-pain", "underlying-belief", "deep-diagnosis", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0293", "Principle",
        "Questioning is revealing, not interrogating -- the posture of deep-digging determines the outcome",
        "Revealing vs interrogating: revealing is driven by curiosity and goodwill, letting the customer see for themselves; interrogating is driven by purpose and pressure, making the customer feel mined. Same question, different posture, completely different result.",
        "Why do some deep questions generate insight while others trigger defensiveness?",
        ["Curiosity is the best disguise, but it's best when it's not a disguise",
         "Interrogation closes; revealing opens",
         "Posture matters more than technique"],
        "People can sense the intent behind a question, even when the question is identical",
        "Source: Consultative Sales Crystal Cluster CH5 C5-03",
        ["revealing-vs-interrogating", "questioning-posture", "curiosity", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0294", "Principle",
        "Renaming the pain point = helping the customer put on new glasses to see their problem",
        "Reframing: restating the customer's pain in new language so it shifts from 'I have a problem' to 'I have a manageable situation'. Renaming is not denying pain; it is giving pain a workable name.",
        "Why does rephrasing the same problem sometimes unlock action?",
        ["Language shapes perception; perception determines action",
         "Good renaming makes an unsolvable problem feel solvable",
         "Renaming requires first fully accepting the original pain"],
        "Linguistic framing influences how people perceive and act on problems",
        "Source: Consultative Sales Crystal Cluster CH5 C5-05",
        ["reframing", "language-shaping", "pain-renaming", "consultative-sales"]))

    # CH6 (3)
    ps.append(make_crystal(
        "KL-PRI-0295", "Principle",
        "A proposal is not a product introduction; it is drawing a path for the customer",
        "Proposal design mindset shift: from 'what features my product has' to 'what your future looks like'. A proposal is a roadmap: present you (pain) -> bridge (solution) -> future you (vision).",
        "What is the essence of proposal design?",
        ["Product features are tools; customers want a roadmap",
         "A good proposal lets customers see their own future",
         "The protagonist of the proposal is the customer, not the product"],
        "People don't buy products; they buy a path from now to their ideal future",
        "Source: Consultative Sales Crystal Cluster CH6 C6-01",
        ["proposal-design", "roadmap", "vision-oriented", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0296", "Principle",
        "Design proposals by subtraction: less = stronger",
        "Subtraction principle: every additional option increases the customer's decision burden. The strongest proposal has just one path (or at most three clear choices). Complex proposals make customers flee; simple proposals make customers act.",
        "Why does offering more choices actually reduce closing rates?",
        ["Too many choices cause decision paralysis",
         "Subtraction proves deep understanding of the customer's needs",
         "A salesperson who dares to subtract has confidence in their own judgment"],
        "Excessive choice leads to decision anxiety and action delay",
        "Source: Consultative Sales Crystal Cluster CH6 C6-04",
        ["subtraction-design", "decision-simplification", "proposal-streamlining", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0297", "Principle",
        "Emotional resonance > logical correctness -- proposals must move the heart before convincing the mind",
        "Dual decision engines: the emotional engine ('does this feel right') starts first; the logical engine ('does this make sense') verifies second. Design order: first make the customer feel 'this is what I want', then confirm 'this also makes sense'.",
        "What is the relationship between emotion and logic in purchase decisions?",
        ["People decide with the heart first, then rationalize with the brain",
         "A purely logical proposal makes people think but not act",
         "Emotional resonance is the action trigger; logic is the guardrail"],
        "Human purchase decisions are fundamentally emotion-driven and logic-verified",
        "Source: Consultative Sales Crystal Cluster CH6 C6-06",
        ["emotional-decision", "logic-verification", "proposal-impact", "consultative-sales"]))

    # CH7 (4)
    ps.append(make_crystal(
        "KL-PRI-0298", "Principle",
        "Closing is not shutting the door; it is helping the customer feel safe to 'begin'",
        "Redefinition of closing: traditional closing = shutting the door (Closing). Consultative closing = opening the door (Opening). Closing is the start of a relationship, not the end of a sales process. Make the customer feel they are 'beginning' rather than 'being trapped'.",
        "What is the psychological meaning of closing?",
        ["The customer's greatest fear after closing is regret",
         "An opening mindset reassures; a closing mindset scares",
         "The best close makes the customer excited, not anxious"],
        "People need to feel they are beginning, not being trapped, when making a commitment",
        "Source: Consultative Sales Crystal Cluster CH7 C7-01",
        ["closing-psychology", "opening-vs-closing", "safe-commitment", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0299", "Principle",
        "Start with small commitments and large commitments will follow",
        "Commitment ladder: small step (fill a form / trial / small experience) -> medium step (official collaboration / standard plan) -> large step (long-term contract / major investment). Each step's success becomes the confidence source for the next.",
        "How to reduce the customer's commitment fear?",
        ["Small commitments are the testing ground for trust",
         "Successful small steps accumulate into courage for big decisions",
         "A salesperson afraid to start small actually lacks confidence in their own product"],
        "People are more willing to make larger commitments on the foundation of prior successful experiences",
        "Source: Consultative Sales Crystal Cluster CH7 C7-04",
        ["commitment-ladder", "small-commitment", "progressive-closing", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0300", "Principle",
        "Silence is the most powerful weapon in closing",
        "Power of silence: after presenting the proposal, stop talking and wait. Silence gives the customer space to process emotions and think. The person who breaks the silence loses the initiative. Silence is not coldness; it is respect and space.",
        "What is the most powerful action at the moment of closing?",
        ["Inability to stay silent is the salesperson projecting their anxiety onto the customer",
         "Silence allows the customer to enter self-dialogue mode",
         "Decisions made in silence are more resolute"],
        "People need internal processing space to make important decisions",
        "Source: Consultative Sales Crystal Cluster CH7 C7-05",
        ["silence-closing", "white-space-power", "art-of-waiting", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0301", "Principle",
        "Closing is a 'joint decision', not one-sided persuasion",
        "Co-decision model: true closing is both parties confirming 'this is the right choice'. The salesperson doesn't say 'you should buy' but asks 'do you feel this is right for you?'. Co-decision gives the customer a sense of sovereignty, reducing regret probability.",
        "Who should be the primary agent in the closing decision?",
        ["Let the customer feel it is their own decision",
         "Co-decisions are more durable than one-sided persuasion",
         "When customers feel sovereign, satisfaction and renewal rates are both higher"],
        "People have higher commitment and satisfaction with decisions they participated in making",
        "Source: Consultative Sales Crystal Cluster CH7 C7-07",
        ["co-decision", "customer-sovereignty", "bilateral-closing", "consultative-sales"]))

    # CH8 (3)
    ps.append(make_crystal(
        "KL-PRI-0302", "Principle",
        "The first 72 hours determine whether the customer will regret -- the golden period after closing",
        "72-hour rule: the first 72 hours after closing are the peak of 'buyer's remorse syndrome'. Every interaction in this period answers the customer's internal question: 'Did I make the right choice?'. Building confirmation in 72 hours = the foundation of a long-term relationship.",
        "What is the most critical time window after closing?",
        ["Closing is not the end; it is day one of relationship management",
         "Silence in the first 72 hours is read as indifference",
         "The quality of managing the first order determines all subsequent orders"],
        "People enter a state of self-doubt after making major decisions",
        "Source: Consultative Sales Crystal Cluster CH8 C8-01",
        ["72-hour-rule", "buyers-remorse", "post-close-management", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0303", "Principle",
        "High-frequency interaction != harassment; rhythm is the key to customer management",
        "Management rhythm: interaction frequency must match the customer's absorption rhythm, not the salesperson's anxiety rhythm. Three rhythm principles: only valuable interactions count, preview the next interaction time, make the customer anticipate rather than dread your appearance.",
        "How frequent should customer interactions be?",
        ["The difference between harassment and care is whether value is provided",
         "Good rhythm makes the customer feel you appear at just the right time",
         "Rhythm matters more than frequency"],
        "People's acceptance of interaction depends on perceived value and rhythm",
        "Source: Consultative Sales Crystal Cluster CH8 C8-02",
        ["interaction-rhythm", "customer-management", "value-interaction", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0304", "Principle",
        "Three conditions for word-of-mouth spread: sense of achievement + sense of identity + sense of safety",
        "Referral model: a customer willing to recommend you to friends needs three simultaneous conditions -- sense of achievement (I actually changed), sense of identity (I identify with this person/brand), sense of safety (recommending won't embarrass me). Missing any one prevents proactive referral.",
        "Under what conditions will customers spontaneously refer?",
        ["Referral is endorsing you with their own social credit",
         "Customers aren't afraid to recommend good things; they're afraid friends will have a bad experience",
         "Safety is the last threshold of referral behavior"],
        "Referral behavior involves risk assessment of personal social credit",
        "Source: Consultative Sales Crystal Cluster CH8 C8-08",
        ["word-of-mouth", "referral-conditions", "social-credit", "consultative-sales"]))

    # CH9 (2)
    ps.append(make_crystal(
        "KL-PRI-0305", "Principle",
        "The essence of price anxiety is not fear of expense but fear of buying wrong",
        "Price anxiety decoded: when a customer says 'too expensive', the real subtext is 'I'm not sure it's worth it'. Handling sequence: receive anxiety (Earth) -> understand concern (Mountain) -> align value (Lake) -> build worth-it feeling (Fire). Discounting immediately is the worst response.",
        "What is the customer really saying when they complain about price?",
        ["Price complaints are fear wearing a disguise",
         "Responding to price anxiety with discounts confirms their worry",
         "Worth-it feeling is built on understanding, not on discounts"],
        "Price resistance is usually a manifestation of value uncertainty",
        "Source: Consultative Sales Crystal Cluster CH9 C9-01",
        ["price-anxiety", "worth-it-feeling", "energy-alignment", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    ps.append(make_crystal(
        "KL-PRI-0306", "Principle",
        "Upgrading is not more but more right -- helping the customer find the next right stage",
        "Upgrade philosophy: upgrading is not selling something more expensive but helping the customer enter the next stage that suits them. Sequence: affirm current results (Wind) -> hear stuck points (Water) -> extend possibilities (Mountain) -> illuminate new future (Fire).",
        "What is the essence of customer upgrading?",
        ["More and more-right are completely different directions",
         "A good upgrade makes the customer feel understood, not exploited",
         "The prerequisite for upgrading is that the customer is truly ready"],
        "Growth is stage-based; each stage requires different support",
        "Source: Consultative Sales Crystal Cluster CH9 C9-07",
        ["customer-upgrade", "stage-matching", "energy-sequence", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    # CH10 (3)
    ps.append(make_crystal(
        "KL-PRI-0307", "Principle",
        "Customers don't buy once; they walk a journey with you -- three-layer relationship evolution",
        "Three-layer evolution: L1 Supplier (you sell, I buy) -> L2 Expert (you know, I ask) -> L3 Advisor (you lead, I follow). Each layer has different trust foundations and interaction modes. The goal of long-term management is reaching L3.",
        "What is the ultimate form of a sales relationship?",
        ["From supplier to advisor is a triple jump of trust",
         "L3 advisor relationship means the customer includes you in their decision circle",
         "Most salespeople stop at L1, thinking the relationship ends with the transaction"],
        "Business relationships have layers, each with different value and stickiness",
        "Source: Consultative Sales Crystal Cluster CH10 C10-01",
        ["relationship-evolution", "three-layers", "long-term-management", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0308", "Principle",
        "Long-term relationships rely on stability, not passion -- consistency is the greatest source of trust",
        "Three aspects of stability: consistent attitude (not changing face under quota pressure), consistent expertise (not wavering with market fluctuations), consistent stance (not changing words for profit). Stability is more powerful than occasional inspiration.",
        "What does a long-term relationship need most?",
        ["Passion fades; stability doesn't",
         "Customers need predictability",
         "A stable person makes others feel safe entrusting important matters"],
        "What people value most in long-term relationships is consistency and predictability",
        "Source: Consultative Sales Crystal Cluster CH10 C10-04",
        ["stability-management", "consistency", "long-term-trust", "consultative-sales"]))

    ps.append(make_crystal(
        "KL-PRI-0309", "Principle",
        "Become 'the first person they think of': calmer + clearer + more on their side",
        "Three conditions for mind share: calmer than the customer (they panic, you don't), clearer than the customer (they're confused, you're not), more on their side than anyone (they're lost, you don't leave). All three combined = you are the first person they think of when something happens.",
        "How to become irreplaceable in the customer's mind?",
        ["Being irreplaceable is not about being the best but about understanding them the most",
         "Calmness and clarity are trainable capabilities",
         "Being on their side is a choice, not a feeling"],
        "When people need help they choose the person who makes them feel most at ease",
        "Source: Consultative Sales Crystal Cluster CH10 C10-05",
        ["mind-share", "irreplaceability", "calm-and-clear", "consultative-sales"]))

    return ps


def build_patterns():
    pats = []

    # CH2 (2)
    pats.append(make_crystal(
        "KL-PAT-0280", "Pattern",
        "Eight-direction energy switching sequence: Wind->Water->Mountain->Fire->Heaven->Earth->Lake->Thunder",
        "Natural energy sequence: Wind (lighten) -> Water (listen) -> Mountain (organize) -> Fire (ignite) -> Heaven (trust) -> Earth (stabilize) -> Lake (connect) -> Thunder (push). This follows the natural rhythm of the human psyche from defense to openness to action. Jumping the sequence causes discomfort.",
        "What is the optimal order for using energy?",
        ["The energy sequence corresponds to layers of psychological openness",
         "Skipping earlier energies and jumping to later ones is forcing",
         "The natural sequence makes dialogue flow like water"],
        "Psychological openness follows a specific energy-acceptance order",
        "Source: Consultative Sales Crystal Cluster CH2 C2-04",
        ["energy-sequence", "eight-directions", "natural-rhythm", "dialogue-pattern"],
        ["ssa-consultant", "resonance"]))

    pats.append(make_crystal(
        "KL-PAT-0281", "Pattern",
        "Energy alignment diagnosis: observe customer state -> judge needed energy -> choose response",
        "Diagnosis three steps: 1) Observe the customer's speech speed, tone, body language. 2) Judge whether they need to be relaxed/heard/organized/ignited/stabilized right now. 3) Choose the matching energy response. Practice: after each conversation, review 'Did I give the right energy?'",
        "How to quickly judge what energy the customer needs right now?",
        ["Fast speech = needs relaxing (Wind) or stabilizing (Earth)",
         "Silence = needs listening (Water) or safety (Earth)",
         "Repeatedly asking the same thing = needs organizing (Mountain)"],
        "External behavior is a signal of internal energy needs",
        "Source: Consultative Sales Crystal Cluster CH2 C2-05",
        ["energy-diagnosis", "behavior-signals", "response-selection", "dialogue-pattern"],
        ["ssa-consultant", "resonance"]))

    # CH3 (2)
    pats.append(make_crystal(
        "KL-PAT-0282", "Pattern",
        "90-second ice-breaking pattern: safety signal -> light opening -> shared problem introduction",
        "90-second three steps: 1) Send safety signals (smile, relaxed posture, don't rush to talk about product). 2) Light opening (start from their world, not yours). 3) Naturally introduce a shared problem ('many people are thinking about this...').",
        "How to build an effective first impression in 90 seconds?",
        ["Not mentioning the product actually makes people want to hear what you say",
         "Starting from their world is the greatest respect",
         "A shared problem builds connection faster than a shared interest"],
        "First-impression formation requires consciously designed steps",
        "Source: Consultative Sales Crystal Cluster CH3 C3-02",
        ["ice-breaking", "90-seconds", "safety-signal", "opening-design"]))

    pats.append(make_crystal(
        "KL-PAT-0283", "Pattern",
        "Relationship deepening ladder: polite -> sincere -> vulnerable -> trusting -> entrusting",
        "Five-level deepening: L1 Polite (platitudes) -> L2 Sincere (honest talk) -> L3 Vulnerable (reveals fears) -> L4 Trusting (entrusts important matters) -> L5 Entrusting (delegates decision authority). Each upgrade requires a triggering event.",
        "Are there identifiable stages in relationship deepening?",
        ["The level the customer is at determines what you can do",
         "Forcing a level-jump collapses the relationship",
         "Every level-up event is a test of the salesperson"],
        "Relationship deepening is ladder-like; each level needs to be triggered and verified",
        "Source: Consultative Sales Crystal Cluster CH3 C3-04",
        ["relationship-ladder", "deepening-pattern", "trust-upgrade", "relationship-management"]))

    # CH4 (2)
    pats.append(make_crystal(
        "KL-PAT-0284", "Pattern",
        "Questioning funnel: open questions -> situation questions -> pain questions -> vision questions",
        "Four-layer funnel: 1) Open ('How have things been?') builds safety. 2) Situation ('What's your current approach?') understands status quo. 3) Pain ('What frustrates you most about this?') touches emotion. 4) Vision ('If this problem were solved, what would that look like?') opens possibility.",
        "What is the optimal questioning structure for need discovery?",
        ["The deeper the funnel, the higher the trust required",
         "Skipping the open question and going straight to pain is like running a red light",
         "Vision questions are the bridge connecting pain points to proposals"],
        "Effective need discovery requires a structured questioning framework",
        "Source: Consultative Sales Crystal Cluster CH4 C4-02",
        ["questioning-funnel", "need-discovery", "structured-questioning", "dialogue-pattern"]))

    pats.append(make_crystal(
        "KL-PAT-0285", "Pattern",
        "Safety-building three actions: no judging + no selling + no rushing",
        "Safety operations: 1) No judging (accept whatever the customer says; no frowning, no head-shaking). 2) No selling (after hearing the need, don't immediately connect to product; confirm understanding first). 3) No rushing (give them time to think; don't say 'so do you want it or not?'). Each action deposits into the safety account.",
        "How to concretely build safety?",
        ["Safety is built drop by drop",
         "One judgment can destroy ten instances of acceptance",
         "Not rushing is respect for the customer's intelligence"],
        "Building safety requires sustained behavioral consistency",
        "Source: Consultative Sales Crystal Cluster CH4 C4-04",
        ["safety-building", "three-actions", "behavioral-consistency", "trust-construction"]))

    # CH5 (2)
    pats.append(make_crystal(
        "KL-PAT-0286", "Pattern",
        "Three-layer pain excavation pattern: behavior layer -> emotion layer -> belief layer questioning",
        "Three-layer excavation scripts: L1 Behavior 'What situation are you currently facing?' -> L2 Emotion 'How does this make you feel?' -> L3 Belief 'What do you think causes this to keep bothering you?'. Pauses and confirmations are needed between each layer.",
        "How to guide the customer step by step to touch deep pain points?",
        ["The jump from behavior to emotion is the most critical",
         "L2 to L3 requires the customer's active cooperation; you can't force-dig",
         "Pauses and confirmations are the lubricant of excavation"],
        "Revealing deep pain requires layered guidance technique",
        "Source: Consultative Sales Crystal Cluster CH5 C5-02",
        ["pain-excavation", "three-layer-guidance", "questioning-scripts", "deep-needs"]))

    pats.append(make_crystal(
        "KL-PAT-0287", "Pattern",
        "Pain renaming operation: receive -> restate -> flip -> confirm",
        "Renaming four steps: 1) Receive original expression ('I hear you saying...'). 2) Restate in their language (confirm understanding). 3) Flip with new frame ('Looking at it from another angle, this is actually...'). 4) Confirm new frame ('Does this perspective help?').",
        "What are the specific operational steps for renaming pain points?",
        ["Receiving is the prerequisite for flipping; flipping without receiving = negating them",
         "Flipping is not denying pain; it is expanding the perspective",
         "Confirming is the act of returning sovereignty to the customer"],
        "Cognitive frame shifts require accepting first, then restructuring",
        "Source: Consultative Sales Crystal Cluster CH5 C5-04",
        ["renaming", "cognitive-flip", "four-step-operation", "pain-handling"]))

    # CH6 (2)
    pats.append(make_crystal(
        "KL-PAT-0288", "Pattern",
        "Three-section proposal architecture: Present (pain) -> Bridge (solution) -> Future (vision)",
        "Proposal presentation template: 1) Present 'Your current situation is... (describe pain in their language)'. 2) Bridge 'We can do this... (clean, clear solution path)'. 3) Future 'Then you will... (concrete, tangible vision)'. Ratio 2:3:5 -- future gets the most space.",
        "How should a proposal be organized for maximum persuasion?",
        ["Present is resonance; bridge is logic; future is motivation",
         "The more specific the vision, the more action-driving it becomes",
         "Describing the present in the customer's language proves you listened"],
        "Persuasive proposals connect current pain to future vision",
        "Source: Consultative Sales Crystal Cluster CH6 C6-02",
        ["three-section-proposal", "proposal-architecture", "vision-painting", "proposal-design"]))

    pats.append(make_crystal(
        "KL-PAT-0289", "Pattern",
        "Subtraction design pattern: list all -> prioritize -> cut to minimum -> confirm",
        "Subtraction four steps: 1) List all possible options. 2) Prioritize based on core needs. 3) Cut to only the most critical 1-3 options. 4) Confirm with customer 'This is what you need most'. The courage to cut comes from deep understanding of needs.",
        "How to make a proposal as simple and powerful as possible?",
        ["Listing everything first gives cutting a basis",
         "The cutting process itself demonstrates professional judgment",
         "Customers seeing a streamlined proposal feel you truly understand them"],
        "Proposal power is inversely proportional to the number of options",
        "Source: Consultative Sales Crystal Cluster CH6 C6-05",
        ["subtraction-design", "proposal-streamlining", "prioritization", "decision-simplification"]))

    # CH7 (3)
    pats.append(make_crystal(
        "KL-PAT-0290", "Pattern",
        "Three-section natural closing: confirm needs -> present proposal -> invite decision",
        "Natural closing three sections: 1) Confirm 'So what matters most to you is... right?' 2) Present 'Based on your situation, I suggest...' 3) Invite 'Do you feel we can get started?' No pressure, just invitation. Don't say 'Do you want to buy?'; say 'Are you ready to begin?'",
        "How to make closing happen naturally rather than forcefully?",
        ["Confirming needs is the last safety net for closing",
         "Inviting rather than pushing changes the entire quality of the interaction",
         "Natural closing requires every prior step to have been done right"],
        "Closing is the natural result of all preceding steps",
        "Source: Consultative Sales Crystal Cluster CH7 C7-02",
        ["natural-closing", "three-section", "invitation-closing", "closing-pattern"]))

    pats.append(make_crystal(
        "KL-PAT-0291", "Pattern",
        "Closing silence pattern: present proposal -> stop talking -> wait -> respond",
        "Silence operation: 1) Clearly present the proposal and invitation. 2) Immediately stop talking (no supplementing, no explaining, no discounting). 3) Endure the silence (count to 30 internally). 4) Wait for the customer to speak first, then respond. Three temptations that break silence: adding explanations, offering discounts, asking 'what do you think?'",
        "What should happen in the blank space after proposing a close?",
        ["In silence every second feels like a minute, but you must endure",
         "The first person to speak makes the first concession",
         "During silence the customer is having an internal dialogue; don't interrupt"],
        "Silence is a powerful communication tool at the closing moment",
        "Source: Consultative Sales Crystal Cluster CH7 C7-06",
        ["closing-silence", "waiting-technique", "silence-art", "closing-pattern"]))

    pats.append(make_crystal(
        "KL-PAT-0292", "Pattern",
        "Small-commitment guidance: micro-action -> small commitment -> medium commitment -> large commitment",
        "Commitment ladder operation: 1) Micro-action (fill a survey / view a case study). 2) Small commitment (attend one experience / one-week trial). 3) Medium commitment (sign a basic plan). 4) Large commitment (long-term partnership / major investment). Invite the next step only after each step succeeds.",
        "How to use a progressive approach to guide large-value closing?",
        ["Micro-actions are zero-risk probes",
         "Each successful step is confidence for the next",
         "Don't skip levels; skipping = losing trust"],
        "Large commitments are accumulated from a series of successful small commitments",
        "Source: Consultative Sales Crystal Cluster CH7 C7-03",
        ["commitment-ladder", "progressive-closing", "small-steps", "trust-accumulation"]))

    # CH8 (3)
    pats.append(make_crystal(
        "KL-PAT-0293", "Pattern",
        "72-hour confirmation pattern: instant thanks -> 24hr check -> 48hr value -> 72hr direction",
        "72-hour operation: 1) At the moment of closing: sincere thanks + restate commitment. 2) Within 24 hours: confirm everything is smooth + answer questions. 3) Within 48 hours: deliver the first small win / small value. 4) Within 72 hours: provide future direction and next step. Every step answers 'You made the right choice'.",
        "What should be done in the 72 hours after closing?",
        ["Instant thanks must be sincere, not templated",
         "The 24hr check captures the critical 'will I regret this?' window",
         "Direction within 72 hours turns anxiety into anticipation"],
        "Systematic post-close follow-up dramatically reduces cancellation rates",
        "Source: Consultative Sales Crystal Cluster CH8 C8-03",
        ["72-hours", "post-close-followup", "confirmation-pattern", "customer-management"]))

    pats.append(make_crystal(
        "KL-PAT-0294", "Pattern",
        "Success evidence accumulation: catch what's done right -> amplify attribution -> give future feeling",
        "Success accumulation operation: 1) Catch what's done right (proactively spot the customer's progress, however small). 2) Amplify attribution ('This result happened because you did X'). 3) Give future feeling ('At this rate, next you'll...'). Let the customer see themselves progressing.",
        "How to keep the customer continuously feeling value?",
        ["Small progress seen = big motivation activated",
         "Attributing to the customer rather than the product strengthens their sovereignty",
         "Future feeling is the greatest driver of continued payment"],
        "People need continuous positive feedback to maintain engagement",
        "Source: Consultative Sales Crystal Cluster CH8 C8-04",
        ["success-evidence", "positive-attribution", "future-feeling", "sustained-management"]))

    pats.append(make_crystal(
        "KL-PAT-0295", "Pattern",
        "30-day relationship deepening model: remind->review / accompany->consensus / small-steps->big-direction",
        "30-day three phases: 1) Days 1-10 'Remind + Review' (remind usage, review first results). 2) Days 11-20 'Accompany + Consensus' (walk through the wall-hitting period, build shared goals). 3) Days 21-30 'Small Steps + Big Direction' (give concrete next steps, draw long-term roadmap).",
        "How should the first month after closing be managed?",
        ["The first month is the relationship-shaping period",
         "The wall-hitting period (days 11-20) is when churn is most likely",
         "Relationship quality at day 30 determines renewal and referral"],
        "The first month's management quality determines the long-term relationship",
        "Source: Consultative Sales Crystal Cluster CH8 C8-05~06",
        ["30-day-model", "relationship-deepening", "wall-hitting-period", "customer-management"]))

    # CH9 (4)
    pats.append(make_crystal(
        "KL-PAT-0296", "Pattern",
        "Price anxiety handling four steps: receive(Earth) -> understand(Mountain) -> align(Lake) -> worth-it(Fire)",
        "Operation sequence: 1) Receive (Earth): 'I understand your concern; this is an important decision'. 2) Understand (Mountain): 'Which part concerns you most?' 3) Align (Lake): connect price to their core need. 4) Worth-it (Fire): 'Imagine yourself after this problem is solved'. No discounts, no arguments.",
        "How should you respond when a customer says it's too expensive?",
        ["Receiving the anxiety is step one; without it, everything after is wasted",
         "Understanding the specific concern enables precise alignment",
         "Worth-it feeling is ignited from within, not proven from outside"],
        "Price objection handling requires following energy sequence",
        "Source: Consultative Sales Crystal Cluster CH9 C9-01",
        ["price-handling", "energy-four-steps", "objection-handling", "consultative-sales"],
        ["ssa-consultant", "resonance"]))

    pats.append(make_crystal(
        "KL-PAT-0297", "Pattern",
        "Advance/retreat judgment: push(Fire*Heaven) / stop(Earth*Water) / stabilize-first(Earth*Mountain)",
        "Three judgments: 1) Push (customer engaged + ready) -> use Fire(ignite) + Heaven(trust) energy to advance. 2) Stop (customer resisting + pressured) -> use Earth(stabilize) + Water(listen) energy to pause. 3) Stabilize first (customer wavering + needs organizing) -> use Earth(stabilize) + Mountain(organize) energy to settle. Misreading the signal = choosing the wrong action.",
        "When to advance, when to stop, when to stabilize?",
        ["Pushing at the wrong moment is worse than not pushing at all",
         "Stopping is not giving up; it is strategic waiting",
         "Stabilize-first is the most underestimated move -- many closes come from stabilizing"],
        "The key to selling is judging the timing of advance/pause/stabilize",
        "Source: Consultative Sales Crystal Cluster CH9 C9-03",
        ["advance-retreat", "push-stop-stabilize", "energy-combinations", "timing-judgment"],
        ["ssa-consultant", "resonance"]))

    pats.append(make_crystal(
        "KL-PAT-0298", "Pattern",
        "Multi-person decision handling: identify roles -> align energy -> address each -> converge consensus",
        "Multi-person operation: 1) Identify roles in the decision system (decision-maker / influencer / gatekeeper / protector). 2) Use different energy for each role (gatekeeper needs safety (Earth); decision-maker needs trust (Heaven)). 3) Address each role's concerns. 4) Converge consensus (make everyone feel attended to).",
        "How to handle multi-person decision situations?",
        ["The customer is not one person but a small system",
         "People behind the scenes often have more influence than those in front",
         "Consensus isn't everyone being enthusiastic; it's no one objecting"],
        "Multi-person decisions require identifying and separately addressing each role's needs",
        "Source: Consultative Sales Crystal Cluster CH9 C9-04",
        ["multi-person-decision", "role-identification", "decision-system", "consensus-building"],
        ["ssa-consultant", "resonance"]))

    pats.append(make_crystal(
        "KL-PAT-0299", "Pattern",
        "Procrastination handling three types: pressure-type->decompress / chaos-type->organize / numb-type->ignite",
        "Three procrastination types mapped: 1) Pressure-type (heart too heavy) -> decompress: use Wind energy to lighten the burden. 2) Chaos-type (heart too chaotic) -> organize: use Mountain energy to help them find clarity. 3) Numb-type (heart too light) -> ignite: use Fire energy to spark inner motivation. Mistyping = ineffective treatment.",
        "What are the root causes of customer procrastination, and how to match solutions?",
        ["Procrastination is not one behavior but three completely different psychological states",
         "Pressure-type needs decompression, not more pressure",
         "Numb-type is the hardest to handle because they don't feel they have a problem"],
        "Procrastination behavior has different psychological mechanisms requiring classified treatment",
        "Source: Consultative Sales Crystal Cluster CH9 C9-06",
        ["procrastination-handling", "three-types", "symptom-energy", "behavioral-psychology"],
        ["ssa-consultant", "resonance"]))

    # CH10 (2)
    pats.append(make_crystal(
        "KL-PAT-0300", "Pattern",
        "Emotional account management: continuous deposits(safety) -> occasional withdrawals(requests) -> maintain positive balance",
        "Emotional account operation: deposit three actions -- receive changes (Wind), organize present (Mountain), give direction (Fire). Withdrawal = making requests / proposing new plans / asking for referrals. Positive balance makes withdrawals smooth; negative balance gets withdrawals rejected. Always deposit more than you withdraw.",
        "How to maintain long-term emotional trust balance?",
        ["Every genuine act of help is a deposit",
         "Check the balance before withdrawing",
         "Emotional accounts cannot be overdrawn; overdraft repair costs are extremely high"],
        "Trust in relationships is like a bank account requiring continuous deposits to allow occasional withdrawals",
        "Source: Consultative Sales Crystal Cluster CH10 C10-03",
        ["emotional-account", "trust-deposits", "long-term-management", "relationship-maintenance"],
        ["ssa-consultant", "resonance"]))

    pats.append(make_crystal(
        "KL-PAT-0301", "Pattern",
        "Three-layer relationship upgrade triggers: over-deliver -> proactively provide insights -> participate in decisions",
        "Upgrade triggers: L1->L2 (Supplier->Expert): beyond product delivery, proactively provide industry insights or advice. L2->L3 (Expert->Advisor): being invited to participate in the customer's important decision discussions. Each upgrade requires a 'key event'.",
        "How to upgrade from supplier to advisor?",
        ["Over-delivering is the ticket to the second layer",
         "Proactive insights change you from seller to someone knowledgeable",
         "Being invited to participate in decisions is the highest proof of trust"],
        "Relationship upgrading requires providing value beyond the transaction itself",
        "Source: Consultative Sales Crystal Cluster CH10 C10-02",
        ["relationship-upgrade", "trigger-events", "value-transcendence", "long-term-management"]))

    # CH11 (2)
    pats.append(make_crystal(
        "KL-PAT-0302", "Pattern",
        "Rejection handling four types: price-type / time-type / uncertainty-type / safety-type",
        "Four rejection types and responses: 1) Price-type ('too expensive') -> rebuild worth-it feeling. 2) Time-type ('not the right time') -> confirm real reason. 3) Uncertainty-type ('let me think about it') -> help organize decision points. 4) Safety-type ('I'm afraid it won't fit') -> give confirmation and guarantees. Each type requires completely different handling.",
        "How to quickly classify rejections and handle them accordingly?",
        ["Rejection is not negation; it is information",
         "Misclassification = ineffective response",
         "Safety-type is most often misclassified as price-type"],
        "Rejections have different psychological roots requiring classified handling",
        "Source: Consultative Sales Crystal Cluster CH11 C11-02",
        ["rejection-handling", "four-types", "psychological-classification", "objection-matching"]))

    pats.append(make_crystal(
        "KL-PAT-0303", "Pattern",
        "Anti-fragility three practices: emotional detachment -> find the main thread in chaos -> slow down under pressure",
        "Anti-fragility operation: 1) Emotional detachment (pull yourself out of the emotion; watch your reaction like watching a movie). 2) Find the main thread in chaos (in the messiest situation, find the one most important clue). 3) Slow down under pressure (the more urgent, the more deliberately slow down). Pressure is not the enemy; it is the textbook for leveling up.",
        "How to transform sales pressure into growth power?",
        ["Emotional detachment is the first step of anti-fragility",
         "Main-thread thinking keeps you on course in chaos",
         "Slowing down is counter-intuitive but the most effective pressure response"],
        "Pressure can become a catalyst for capability upgrade",
        "Source: Consultative Sales Crystal Cluster CH11 C11-03",
        ["anti-fragility", "pressure-transformation", "emotional-detachment", "inner-practice"]))

    # CH12 (1)
    pats.append(make_crystal(
        "KL-PAT-0304", "Pattern",
        "Five-act drama: Establish(Wind*Water) -> Explore(Water->Mountain) -> Vision(Fire) -> Action(Mountain->Fire->Heaven) -> Commit(Heaven*Thunder)",
        "Five-act complete flow: 1) Establish act (Wind+Water: lighten+listen, build safe relationship). 2) Explore act (Water->Mountain: deep listen+organize, discover needs and pain). 3) Vision act (Fire: ignite, let customer see possible future). 4) Action act (Mountain->Fire->Heaven: organize proposal+ignite action+build trust). 5) Commit act (Heaven+Thunder: trust+push, natural close).",
        "How should a complete consultative sales conversation be arranged?",
        ["The five acts follow natural psychological rhythm, not artificial design",
         "Each act has its own dominant energy",
         "Skipping acts is the most common sales mistake"],
        "Sales conversations have a natural dramatic structure corresponding to specific energy arrangements",
        "Source: Consultative Sales Crystal Cluster CH12 C12-01",
        ["five-act-drama", "energy-arrangement", "conversation-choreography", "complete-flow"],
        ["ssa-consultant", "resonance"]))

    return pats


def build_lessons():
    ls = []

    ls.append(make_crystal(
        "KL-LES-0240", "Lesson",
        "Most common sales mistake: rushing to talk about the product and forgetting to listen first",
        "Error pattern: customer hasn't finished speaking and you start introducing the product -> customer feels pushed -> defense mechanism activates -> closing probability drops sharply. Fix: force yourself to only ask and listen for the first 10 minutes; don't talk about the product.",
        "Why is the first move of most salespeople already wrong?",
        ["Rushing to talk is the salesperson's anxiety, not the customer's need",
         "Listening first feels slow but produces faster results",
         "10 minutes of listening saves 1 hour of ineffective pitching"],
        "Salespeople tend to prematurely enter pitch mode due to anxiety",
        "Source: Consultative Sales Crystal Cluster CH1 Common Errors",
        ["rushing-to-pitch", "listening-deficit", "sales-error", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0241", "Lesson",
        "Cost of energy misalignment: customer needs stabilizing but you're pushing",
        "Typical scenario: customer is hesitant (needs Earth/Mountain energy to stabilize and organize), salesperson uses Fire/Thunder energy to push -> customer's panic escalates -> flees or reluctantly agrees then cancels. Energy misalignment is more destructive than not speaking at all.",
        "Why does trying harder drive customers away?",
        ["Not seeing what energy the customer needs is the salesperson's biggest blind spot",
         "Energy misalignment makes the customer feel you don't understand them",
         "When unsure which energy to use, silence (Earth) is the safest"],
        "Sales failure often stems not from insufficient effort but from misdirection",
        "Source: Consultative Sales Crystal Cluster CH2 Common Errors",
        ["energy-misalignment", "over-pushing", "sales-failure", "direction-error"],
        ["ssa-consultant", "resonance"]))

    ls.append(make_crystal(
        "KL-LES-0242", "Lesson",
        "Relationship building error: treating 'finding shared interests' as the entirety of connection",
        "Wrong assumption: chatting about shared interests = relationship established. Truth: shared interests are only surface-level connection that fades over time. Only shared problem-solving experiences build deep connection. Many salespeople stuck at 'great chat but no close' are stopped at this layer.",
        "Why do some customers chat well with you but never close?",
        ["Chatting well does not equal trust",
         "Surface connection cannot support business decisions",
         "Shifting from chatting about interests to discussing problems is a deliberate transition"],
        "Social friendliness does not equate to business trust",
        "Source: Consultative Sales Crystal Cluster CH3 Common Errors",
        ["shallow-connection-trap", "friendliness-not-trust", "relationship-building-error", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0243", "Lesson",
        "Need discovery error: asking about pain first is like surgery before anesthesia",
        "Wrong sequence: skip open and situation questions, directly ask 'What problems do you have?' -> customer feels interrogated -> gives surface answers or goes defensive. Correct order: build safety first -> explore context -> only then touch pain.",
        "Why does directly asking questions sometimes fail to get real answers?",
        ["Without safety, no environment for truth-telling",
         "Pain points need to be guided to surface, not forced out",
         "The questioning sequence itself communicates your attitude"],
        "Deep needs surface only with safety and the right questioning sequence",
        "Source: Consultative Sales Crystal Cluster CH4 Common Errors",
        ["wrong-question-order", "lack-of-safety", "need-discovery-failure", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0244", "Lesson",
        "Pain deep-dig error: turning revealing into interrogating, causing customer to close rather than open",
        "Wrong posture: approaching with 'I need to dig out your pain points to sell you something' -> customer senses the exploitative intent -> defense wall goes up -> even the best questions yield nothing. Fix: approach with genuine curiosity and goodwill to understand.",
        "Why do some deep questions make customers more closed off?",
        ["Customers can sense your questioning intent",
         "Interrogating mindset and exploring mindset produce completely different question quality",
         "The best disguise is not disguising -- genuinely be curious about them"],
        "Questioning intent matters more than questioning technique",
        "Source: Consultative Sales Crystal Cluster CH5 Common Errors",
        ["interrogation-mindset", "wrong-intent", "deep-dig-failure", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0245", "Lesson",
        "Proposal design error: offering too many options leading to decision paralysis",
        "Choice overload trap: salesperson lays out all options -> customer sees 5-6 choices -> cannot compare -> decision paralysis -> 'let me think about it' -> never comes back. Fix: filter to 1-3 for them; use subtraction to demonstrate expertise.",
        "Why does offering more proposals actually reduce closing rates?",
        ["Too many choices is laziness in helping the customer make judgments",
         "'Giving you many choices' is not considerate; it is abdication of responsibility",
         "A salesperson who dares to use subtraction is the real expert"],
        "Excessive choice consumes decision energy, leading to delay or abandonment",
        "Source: Consultative Sales Crystal Cluster CH6 Common Errors",
        ["choice-overload", "decision-paralysis", "proposal-design-error", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0246", "Lesson",
        "Closing error: unable to resist talking after presenting, breaking the closing silence",
        "Fatal action: after presenting the proposal, nervousness drives continued supplementing, explaining, or even proactive discounting -> signal received by customer is 'even they're not sure' -> trust wavers -> no buy. Fix: after presenting the proposal, shut up and let silence work for you.",
        "What is the most common mistake at the moment of closing?",
        ["Talking too much is leaking anxiety",
         "Proactively discounting is the biggest signal of lacking product confidence",
         "Silence is uncomfortable but makes closing happen"],
        "Talking too much at the closing moment is a universal and fatal error",
        "Source: Consultative Sales Crystal Cluster CH7 Common Errors",
        ["breaking-silence", "closing-anxiety", "over-talking-failure", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0247", "Lesson",
        "Customer management error: disappearing after closing, leaving the 72-hour golden period empty",
        "Fatal omission: after closing, rushing to find the next customer -> no follow-up in first 72 hours -> customer at their most vulnerable feels abandoned -> cancels or never contacts you again. Fix: the 72 hours after closing matter more than everything before closing.",
        "Why do some customers become dissatisfied after closing?",
        ["Post-close silence is read as 'got the money and stopped caring'",
         "72 hours is the peak of buyer's remorse",
         "One good follow-up is worth ten good pitches"],
        "Immediately disappearing after closing is one of the biggest causes of customer churn",
        "Source: Consultative Sales Crystal Cluster CH8 Common Errors",
        ["post-close-disappearance", "72-hour-void", "customer-churn", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0248", "Lesson",
        "Price handling error: discounting when the customer says expensive -- the fastest way to destroy worth-it feeling",
        "Chain reaction: customer says too expensive -> immediately discount -> customer confirms 'it really wasn't worth that price' -> even if they buy they feel cheated -> no referrals, no renewals. Discounting tells the customer: the original price was a lie.",
        "Why does discounting actually make closing harder?",
        ["Discounting is negating your own value",
         "What customers remember is not the discount but the fact you were willing to lower the price",
         "Responding to price anxiety with discounts confirms their suspicion"],
        "Immediate price concession fundamentally damages perceived product value",
        "Source: Consultative Sales Crystal Cluster CH9 Common Errors",
        ["discount-trap", "worth-it-destruction", "price-concession", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0249", "Lesson",
        "Long-term management error: only appearing when there's something to sell",
        "Relationship damage pattern: no interaction normally -> new product to push -> suddenly warm -> customer sees through it -> feels used as a tool -> relationship downgrades. Fix: provide value continuously, not only when you need to sell something.",
        "Why do some long-term customers suddenly stop responding?",
        ["Highly purposeful interaction gets detected",
         "Appearing only with sales intent = withdrawing without depositing",
         "Customers judge whether you genuinely care by looking at when you appear"],
        "Utilitarian interaction in relationships progressively erodes trust",
        "Source: Consultative Sales Crystal Cluster CH10 Common Errors",
        ["utilitarian-interaction", "trust-erosion", "long-term-management-error", "consultative-sales"]))

    ls.append(make_crystal(
        "KL-LES-0250", "Lesson",
        "Inner practice error: treating rejection as personal negation rather than objective information",
        "Emotional trap: customer says no -> salesperson internally translates to 'I'm not good / my product isn't good / they don't like me' -> confidence damaged -> next customer performance worsens -> vicious cycle. Fix: rejection is information not negation; analyzing reasons is more useful than self-blame.",
        "Why do some salespeople lose confidence the longer they do it?",
        ["Personalizing rejection is the root of sales burnout",
         "The same rejection can be diagnosis or poison depending on interpretation",
         "Masters turn rejections into data; novices turn rejections into trauma"],
        "How rejection is interpreted determines the salesperson's long-term performance",
        "Source: Consultative Sales Crystal Cluster CH11 Common Errors",
        ["rejection-interpretation", "personalization-trap", "sales-burnout", "inner-practice"]))

    ls.append(make_crystal(
        "KL-LES-0251", "Lesson",
        "Integration error: it's not what you say that's wrong, but when you say it and with what energy",
        "Misalignment scenario: correct content expressed at the wrong time with the wrong energy -> zero effect or backfire. Example: discussing vision when the customer is anxious (wrong timing), using push energy when stabilization is needed (wrong energy). Timing x Energy x Content must all align.",
        "Why are the same words sometimes effective and sometimes not?",
        ["Sales is not just a content problem; it is a timing and energy problem",
         "All three must align for power; any one misaligned and it's ineffective",
         "This is the hardest to train but the most important integration skill"],
        "Sales effectiveness depends on the alignment of content, timing, and energy",
        "Source: Consultative Sales Crystal Cluster CH12 Common Errors",
        ["timing-misalignment", "energy-misalignment", "integration-skill", "practical-error"],
        ["ssa-consultant", "resonance"]))

    return ls


def main():
    principles = build_principles()
    patterns = build_patterns()
    lessons = build_lessons()

    print(f"Principles: {len(principles)}")
    print(f"Patterns: {len(patterns)}")
    print(f"Lessons: {len(lessons)}")
    total_new = len(principles) + len(patterns) + len(lessons)
    print(f"Total new: {total_new}")

    # Load existing
    with open(CRYSTALS_PATH, "r", encoding="utf-8") as f:
        existing = json.load(f)
    print(f"Existing crystals: {len(existing)}")

    # Append
    all_new = principles + patterns + lessons
    existing.extend(all_new)
    print(f"Total after append: {len(existing)}")

    # Write
    with open(CRYSTALS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print("Done writing to crystals.json")

    # Verify
    with open(CRYSTALS_PATH, "r", encoding="utf-8") as f:
        verify = json.load(f)
    print(f"Verified total: {len(verify)}")
    print(f"Expected: 1174")
    print(f"Match: {len(verify) == 1174}")

    # List new CUIDs
    print("\n--- New CUIDs ---")
    for c in all_new:
        print(f"  {c['cuid']} ({c['crystal_type']}): {c['g1_summary'][:60]}...")


if __name__ == "__main__":
    main()
