# Research Methodology: FBIHM Inventory Engine

This document outlines the systematic process followed during the development and research of the **FBIHM Inventory Engine**.

---

## 1. Research Design
The study employed an **Applied Research** design using the **Experimental Software Engineering** approach. The goal was to build a functional prototype that solves real-world inventory problems and measure its effectiveness.

## 2. Software Development Life Cycle (SDLC)
We utilized the **Agile Development Model**, specifically **Scrum**, which allowed for:
- **Sprints:** Developing individual modules (Auth, Inventory, POS) in 2-week cycles.
- **Continuous Feedback:** Testing the UI with potential users early in the process.
- **Flexibility:** Easily migrating from SQLite to MongoDB when scalability requirements became clear.

## 3. Data Collection Methods
- **Interviews:** Informal discussions with 3 small business owners to identify "pain points" in their current manual systems.
- **Observation:** Watching the current checkout process in local "Sari-sari" stores to understand high-speed transaction needs.
- **System Logs:** Automatically generated logs during the testing phase to identify common user errors and system crashes.

## 4. Technical Stack Justification
- **Python (Flask):** Chosen for its rapid development capabilities and extensive library support for data processing (Pandas).
- **MongoDB:** Chosen over SQL to handle the "Unstructured" nature of retail items (where different items have different metadata).
- **SocketIO:** Chosen to fulfill the requirement for **Real-Time Visibility**, essential for preventing double-selling of the last stock item.

## 5. Development Phases
1.  **Requirement Analysis:** Defining the core features (Stock tracking, POS, Reporting).
2.  **System Design:** Drafting the NoSQL schema and the "Facebook-style" UI wireframes.
3.  **Implementation:** Coding the Flask backend and dynamic JavaScript frontend.
4.  **Integration & Testing:** Connecting the modules and running stress tests on the database.
5.  **Deployment:** Setting up the GitHub Actions CI/CD and the 24/7 Watchdog daemon.

## 6. Verification & Validation
- **Functional Testing:** Ensuring every button and route performs its intended action.
- **Performance Testing:** Measuring the response time of the POS checkout under simulated load.
- **User Validation:** A final walkthrough with a store manager to confirm that the system meets business needs.
