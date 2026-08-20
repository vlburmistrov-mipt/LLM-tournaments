# Summary of Nature Human Behaviour Paper

**Title**: Playing repeated games with large language models  
**Authors**: Elif Akata, Lion Schulz, Julian Coda-Forno, Seong Joon Oh, Matthias Bethge, Eric Schulz (*Nature Human Behaviour*, Vol. 9, July 2025, pp. 1380–1390)  
**DOI**: [10.1038/s41562-025-02172-y](https://doi.org/10.1038/s41562-025-02172-y)

---

## 1. Executive Summary & Motivation
As Large Language Model (LLM) agents increasingly interact with humans and other autonomous agents in shared environments, understanding their social and strategic behavior is crucial. This paper applies **behavioural game theory** to systematically study LLMs' cooperation and coordination across finitely repeated  	imes 2$ games, playing against each other, human-like heuristic strategies, and actual human players.

---

## 2. Experimental Setup
- **Games Studied**: Finitely repeated  	imes 2$ games across various economic and strategic families (Prisoner's Dilemma, Coordination games, Win-Win games, Battle of the Sexes, etc.).
- **Opponents**: LLMs playing against other LLMs, rule-based human-like strategies (e.g., Tit-for-Tat, Alternators), and real human participants.
- **Intervention & Prompting**: Testing robustness checks, payoff modifications, opponent information provision, and "social chain-of-thought" (asking models to predict opponent actions first).

---

## 3. Key Findings & Insights
1. **Strong Performance in Self-Interested Games**: Surprisingly, LLMs perform exceptionally well in self-interested competitive games such as the iterated Prisoner's Dilemma family—frequently outperforming typical human benchmarks in avoiding mutual defection traps.
2. **Coordination Deficits**: In contrast, LLMs behave suboptimally in games requiring **coordination** (such as Battle of the Sexes), where multiple conflicting equilibria exist. They fail to establish alternating or fair sharing conventions with simple human-like alternating agents, rendering them uncoordinated in these settings.
3. **Model Scaling**: Larger LLMs consistently outperform smaller ones. GPT-4 performed best overall, significantly outperforming Claude 2, Davinci models, and Llama 2.
4. **Behavioral Modulation**:
   - **Forgiveness**: Instructing or prompting models about opponent mistakes can make them more forgiving.
   - **Social Chain-of-Thought**: Asking GPT-4 to explicitly predict the opponent's next move before making its own decision drastically improves coordination success, particularly when interacting with human players.

---

## 4. Significance
This study establishes foundational empirical insights into the social decision-making of LLMs, demonstrating that while LLMs excel in strategic self-interest, coordination remains a key bottleneck—paving the way toward a rigorous **"behavioural game theory for machines"**.
