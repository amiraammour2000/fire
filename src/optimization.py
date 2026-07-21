from ortools.linear_solver import pywraplp

def optimize_aircraft_dispatch(zones_data, available_aircrafts):
    """
    Résout un problème d'affectation (Assignment Problem) sous contraintes via OR-Tools.
    Objectif : Minimiser le score de risque (Propagation * Priorité) non couvert par la capacité des avions.
    """
    if not zones_data or available_aircrafts <= 0:
        return []

    num_zones = len(zones_data)
    # Chaque avion a une capacité d'extinction théorique de 1 unité
    # On crée une matrice de coûts : Coût = Taux de propagation * Facteur de priorité
    costs = []
    for z in zones_data:
        priority_factor = 3.0 if z['priority'] == 'Critique' else 1.0
        cost = z['spread_rate'] * priority_factor
        costs.append(cost)

    # Création du solveur MIP (Mixed Integer Programming)
    solver = pywraplp.Solver.CreateSolver('CBC')
    if not solver:
        return [{"error": "Solveur non disponible"}]

    # Variables de décision : x[i][j] = 1 si l'avion j est assigné à la zone i
    x = {}
    for i in range(num_zones):
        for j in range(available_aircrafts):
            x[i, j] = solver.IntVar(0, 1, f'x_{i}_{j}')

    # Contrainte 1: Un avion ne peut être qu'à un seul endroit à la fois
    for j in range(available_aircrafts):
        solver.Add(sum(x[i, j] for i in range(num_zones)) <= 1)

    # Contrainte 2: Limiter le nombre d'avions par zone pour éviter la saturation de l'espace aérien (max 4)
    max_per_zone = 4
    for i in range(num_zones):
        solver.Add(sum(x[i, j] for j in range(available_aircrafts)) <= max_per_zone)

    # Fonction Objectif : Minimiser le coût total des zones NON couvertes (ou couvertes partiellement)
    # On pénalise le fait de ne pas mettre d'avion là où le coût est élevé
    objective = []
    for i in range(num_zones):
        aircraft_assigned = sum(x[i, j] for j in range(available_aircrafts))
        # Coût résiduel = Coût de la zone - (Nombre d'avions * réduction unitaire)
        residual_risk = costs[i] - (aircraft_assigned * (costs[i] / 2.0))
        objective.append(residual_risk)

    solver.Minimize(sum(objective))

    # Résolution
    status = solver.Solve()

    allocation = []
    if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
        for i in range(num_zones):
            assigned_count = sum(x[i, j].solution_value() for j in range(available_aircrafts))
            allocation.append({
                "zone": zones_data[i]['name'],
                "avions_assignes": int(assigned_count),
                "risque_residuel": round(costs[i] - (assigned_count * (costs[i] / 2.0)), 2)
            })
    return allocation