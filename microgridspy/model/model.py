import xarray as xr
import linopy
import os

from typing import Optional, Dict
from pathlib import Path

from config.solver_settings import get_solver_settings
from microgridspy.model.parameters import ProjectParameters
from microgridspy.model.initialize import (
    initialize_sets, 
    initialize_demand, 
    initialize_resource, 
    initialize_temperature,
    initialize_fuel_cost,
    initialize_grid_availability,
    initialize_project_parameters, 
    initialize_res_parameters, 
    initialize_battery_parameters,
    initialize_generator_parameters,
    initialize_thermal_demand,
    initialize_compressor_parameters,
    initialize_grid_parameters,
    initialize_tes_parameters,
)
from microgridspy.model.variables import (
    add_project_variables, 
    add_res_variables,
    add_lost_load_variables,
    add_battery_variables,
    add_generator_variables,
    add_compressor_variables,
    add_grid_variables,
    add_tes_variables,
)

from microgridspy.model.constraints.project_costs import add_cost_calculation_constraints
from microgridspy.model.constraints.energy_balance import add_energy_balance_constraints
from microgridspy.model.constraints.conversion_constraints import add_minimum_conversion_size_constraints
from microgridspy.model.constraints.res_constraints import add_res_constraints
from microgridspy.model.constraints.battery_constraints import add_battery_constraints
from microgridspy.model.constraints.generator_constraints import add_generator_constraints
from microgridspy.model.constraints.grid_constraints import add_grid_constraints
from microgridspy.model.constraints.project_emissions import add_project_emissions
from microgridspy.model.constraints.compressor_constraints import add_compressor_constraints
from microgridspy.model.constraints.TES_constraints import add_tes_constraints

# Define the Model class
class Model:
    def __init__(self, settings: ProjectParameters) -> None:
        """Initialize the Model class."""
        # Store project parameters for settings and user inputs
        self.settings: ProjectParameters = settings
        
        # Define system components
        self.has_battery: bool = settings.project_settings.system_configuration in [0, 1]
        self.has_generator: bool = settings.project_settings.system_configuration in [0, 2]
        self.has_grid_connection: bool = settings.advanced_settings.grid_connection
        self.has_compressor: bool = settings.advanced_settings.use_compressor
        self.has_tes: bool = settings.advanced_settings.use_tes

        # Initialize linopy model
        self.model = linopy.Model()
        self.sets: xr.Dataset = xr.Dataset()
        self.time_series: xr.Dataset = xr.Dataset()
        self.parameters: xr.Dataset = xr.Dataset()
        self.variables: Dict[str, linopy.Variable] = {}
        self.solution = None
        
        print("Model initialized.")

    def _initialize_sets(self) -> None:
        """Definition of sets (or dimensions)."""
        self.sets: xr.Dataset = initialize_sets(self.settings, self.has_generator)
        print("Sets initialized successfully.")

    def _initialize_time_series(self) -> None:
        """Load and initialize time series data."""
        self.demand: xr.DataArray = initialize_demand(self.sets)
        self.resource: xr.DataArray = initialize_resource(self.sets)
        self.temperature: xr.DataArray = initialize_temperature(self.sets)
        self.thermal_demand: xr.DataArray = initialize_thermal_demand(self.sets)

        # Combine time series data into a single xr.Dataset
        self.time_series: xr.Dataset = xr.merge([self.demand.to_dataset(name='DEMAND'),
                                                 self.thermal_demand.to_dataset(name='THERMAL_DEMAND'),
                                                 self.resource.to_dataset(name='RESOURCE'),
                                                 self.temperature.to_dataset(name='TEMPERATURE'),])
        if self.has_grid_connection:
            self.grid_availability: xr.DataArray = initialize_grid_availability(self.sets)
            self.time_series = xr.merge([self.time_series, self.grid_availability.to_dataset(name='GRID_AVAILABILITY')])
        
        print("Time series data loaded and initialized successfully.")

    def _initialize_parameters(self) -> None:
        """Initialize the model parameters."""
        self.project_parameters: xr.Dataset = initialize_project_parameters(self.settings, self.sets)
        self.res_parameters: xr.Dataset = initialize_res_parameters(self.settings, self.sets)

        # Combine parameters into a single xr.Dataset
        self.parameters: xr.Dataset = xr.merge([self.time_series,self.project_parameters, self.res_parameters])
        
        if self.has_battery:
            self.battery_parameters: xr.Dataset = initialize_battery_parameters(self.settings, self.time_series, self.sets)
            self.parameters = xr.merge([self.parameters, self.battery_parameters])

        if self.has_generator:
            self.generator_parameters: xr.Dataset = initialize_generator_parameters(self.settings, self.sets)
            self.parameters = xr.merge([self.parameters, self.generator_parameters])

            self.fuel_cost: xr.DataArray = initialize_fuel_cost(self.sets)
            self.parameters = xr.merge([self.parameters, self.fuel_cost.to_dataset(name='FUEL_SPECIFIC_COST')])

        if self.has_grid_connection:
            self.grid_parameters: xr.Dataset = initialize_grid_parameters(self.settings, self.sets)
            self.parameters = xr.merge([self.parameters, self.grid_parameters])
        
        if self.has_compressor:
            self.compressor_parameters: xr.Dataset = initialize_compressor_parameters(self.settings, self.sets)
            self.parameters = xr.merge([self.parameters, self.compressor_parameters])

        if self.has_tes:
            self.tes_parameters: xr.Dataset = initialize_tes_parameters(self.settings, self.sets)
            self.parameters = xr.merge([self.parameters, self.tes_parameters])

        print("Parameters initialized successfully.")

    def _add_variables(self) -> None:       
        """Add variables to the model."""
        self.project_variables: Dict[str, linopy.Variable] = add_project_variables(self.model, self.settings, self.sets)
        self.res_variables: Dict[str, linopy.Variable] = add_res_variables(self.model, self.settings, self.sets)
        self.variables: Dict[str, linopy.Variable] = {**self.project_variables, **self.res_variables}

        if self.has_battery:
            self.battery_variables: Dict[str, linopy.Variable] = add_battery_variables(self.model, self.settings, self.sets)
            self.variables.update(self.battery_variables)

        if self.has_generator:
            self.generator_variables: Dict[str, linopy.Variable] = add_generator_variables(self.model, self.settings, self.sets)
            self.variables.update(self.generator_variables)

        if self.has_grid_connection:
            self.grid_variables: Dict[str, linopy.Variable] = add_grid_variables(self.model, self.settings, self.sets)
            self.variables.update(self.grid_variables)

        if self.settings.project_settings.lost_load_fraction > 0:
            self.lost_load_variables: Dict[str, linopy.Variable] = add_lost_load_variables(self.model, self.settings, self.sets)
            self.variables.update(self.lost_load_variables)

        if self.has_compressor:
            self.compressor_variables = add_compressor_variables(
                self.model, self.settings, self.sets
            )
            self.variables.update(self.compressor_variables)
        
        if self.has_tes:
            self.tes_variables = add_tes_variables(self.model, self.settings, self.sets)
            self.variables.update(self.tes_variables)

        print("Variables added to the model successfully.")

    def _add_constraints(self) -> None:
        """Add constraints to the model."""
        add_res_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)
        add_cost_calculation_constraints(self.model, self.settings, self.sets, self.parameters, self.variables, self.has_battery, self.has_generator, self.has_compressor, self.has_grid_connection, self.has_tes)
        add_energy_balance_constraints(self.model, self.settings, self.sets, self.parameters, self.variables, self.has_battery, self.has_generator, self.has_compressor, self.has_grid_connection, self.has_tes)
        add_minimum_conversion_size_constraints(self.model, self.settings, self.sets, self.parameters, self.variables, self.has_battery, self.has_generator, self.has_grid_connection)
        
        if self.has_battery:
            add_battery_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)

        if self.has_generator:
            add_generator_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)

        if self.has_grid_connection:
            add_grid_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)

        if self.settings.advanced_settings.multiobjective_optimization:
            add_project_emissions(self.model, self.settings, self.sets, self.parameters, self.variables, self.has_battery, self.has_generator, self.has_grid_connection)

        if self.has_compressor:
            add_compressor_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)

        if self.has_tes:
            add_tes_constraints(self.model, self.settings, self.sets, self.parameters, self.variables)
        
        print("Constraints added to the model successfully.")

    def _build(self) -> None:
        self._initialize_sets()
        print("\n--- DEBUG SETS ---")
        print("years values:", self.sets.years.values)
        print("years dims:", self.sets.years.dims)
        print("periods values:", self.sets.periods.values)
        print("periods dims:", self.sets.periods.dims)
        print("-------------------\n")
        self._initialize_time_series()
        self._initialize_parameters()
        self._add_variables()
        print("\n--- DEBUG TES VARIABLES ---")
        for name in self.variables:
            if "tes" in name:
                print(name, "dims:", self.variables[name].dims)
        print("----------------------------\n")

        self._add_constraints()

    def _solve(self, solver: str, problem_fn: Optional[str] = None, log_file_path: Optional[str] = None):
        """
        Solve the model using a specified solver or a default one.

        Parameters:
        - solver: The name of the solver to use.
        - problem_fn: The file path for saving the solver's problem formulation. If not provided, no file will be saved.
        - log_file_path: The file path for logging the solver's output. If not provided, no log will be saved.
        """

        # Ensure the solver is available
        if solver not in linopy.available_solvers:
            print(f"Solver {solver} not available. Choose from {linopy.available_solvers}.")
            return None

        # Get solver settings based on the selected solver and MILP formulation
        solver_options = get_solver_settings(solver, self.settings.advanced_settings.milp_formulation)

        # Handle problem file path if specified
        if problem_fn:
            try:
                problem_fn = Path(problem_fn)  # Convert to Path object
                problem_dir = problem_fn.parent
                if not problem_dir.exists():
                    problem_dir.mkdir(parents=True, exist_ok=True)
                print(f"Saving problem formulation to {problem_fn}")
            except Exception as e:
                print(f"Error with problem file path: {e}. Proceeding without saving the problem formulation.")
                problem_fn = None

        # Handle log file path if specified
        if log_file_path:
            try:
                log_file_path = Path(log_file_path)  # Convert to Path object
                log_dir = log_file_path.parent
                if not log_dir.exists():
                    log_dir.mkdir(parents=True, exist_ok=True)
                print(f"Using log file at {log_file_path}")
            except Exception as e:
                print(f"Error with log file path: {e}. Proceeding without a log file.")
                log_file_path = None  

        # Attempt to solve the model
        print(f"Solving the model using {solver}...")
        try:
            self.model.solve(solver_name=solver, problem_fn=problem_fn, log_fn=log_file_path, **solver_options)
        except Exception as e:
            raise RuntimeError(f"Error during solving: {e}")

        self.solution = self.model.solution

        if hasattr(self, "time_series") and "THERMAL_DEMAND" in self.time_series:
            try:
                th = self.time_series["THERMAL_DEMAND"]
                th_ds = th.to_dataset(name="THERMAL_DEMAND")
                self.solution = xr.merge([self.solution, th_ds])
                print("THERMAL_DEMAND added to solution.")
            except Exception as e:
                print(f"Error adding THERMAL_DEMAND to solution: {e}")

        return self.solution
    
    def solve_single_objective(self, solver: str, problem_fn: Optional[str] = None, log_path: Optional[str] = None):
        """Solve the model for a single objective based on the project's optimization goal."""
        # Build the model
        self._build()

        # Define the objective function
        if self.settings.project_settings.optimization_goal == 0:
            # Minimize Net Present Cost (NPC)
            npc_objective = (self.variables["scenario_net_present_cost"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
            self.model.add_objective(npc_objective)
            print("Objective function: Minimize Net Present Cost (NPC) added to the model.")
        else:
            # Minimize Total Variable Cost
            variable_cost_objective = (self.variables["total_scenario_variable_cost_nonact"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
            self.model.add_objective(variable_cost_objective)
            print("Objective function: Minimize Total Variable Cost added to the model.")

        solution = self._solve(solver, problem_fn, log_path)

        return solution
    
    # Solve the multi-objective optimization problem to generate a Pareto front
    def solve_multi_objective(self, num_points: int, solver: str, problem_fn: Optional[str] = None, log_path: Optional[str] = None):
        """Solve the multi-objective optimization problem to generate a Pareto front."""
        self._build()
        # Define the objective function
        if self.settings.project_settings.optimization_goal == 0:
            # Minimize Net Present Cost (NPC)
            cost_objective = (self.variables["scenario_net_present_cost"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
            cost_objective_variable = "Net Present Cost"
        else:
            # Minimize Total Variable Cost
            cost_objective = (self.variables["total_scenario_variable_cost_nonact"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
            cost_objective_variable = "Total Variable Cost"

        solutions = []
        print(f"Starting multi-objective optimization with {num_points} pareto points...")
        # Step 1: Minimize NPC without CO₂ constraint (max CO₂ emissions)
        print("Step 1: Minimize NPC without CO₂ constraint (max CO₂ emissions)")
        self.model.add_objective(cost_objective)
        solution = self._solve(solver, problem_fn, log_path)
        solutions.append(solution)
        # Extract max CO₂ emissions from solution
        max_co2 = solution.get("Total CO2 Emissions").values
        print(f"Max CO₂ emissions: {max_co2 / 1000} tonCO₂")

        # Step 2: Minimize CO₂ emissions without NPC constraint (max NPC)
        print("Step 2: Minimize CO₂ emissions without NPC constraint (max NPC)")
        emissions_objective = (self.variables["scenario_co2_emission"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
        self.model.add_objective(emissions_objective, overwrite=True)
        solution = self._solve(solver, problem_fn, log_path)
        min_co2 = solution.get("Total CO2 Emissions").values
        solutions.append(solution)
        print(f"Min CO₂ emissions: {min_co2 / 1000} tonCO₂")

        # Initialize lists to store Pareto front data
        npc_values = []
        co2_values = []

        # Calculate step size for emissions thresholds
        emission_step = (max_co2 - min_co2) / (num_points - 1)

        # Generate Pareto front
        for i in range(num_points):
            # Define the current CO₂ emission threshold
            emission_threshold = min_co2 + i * emission_step
            print(f"Step {i+2}: Minimize NPC under CO₂ constraint: {emission_threshold / 1000} tonCO₂")
            total_emissions = (self.variables["scenario_co2_emission"] * self.parameters['SCENARIO_WEIGHTS']).sum('scenarios')
            self.model.add_constraints(total_emissions <= emission_threshold, name=f"co2_threshold_{i}")

            # Minimize NPC under this CO₂ constraint
            self.model.add_objective(cost_objective, overwrite=True)
            solution = self._solve(solver, problem_fn, log_path)
            solutions.append(solution)

            # Collect results
            npc_values.append(solution.get(cost_objective_variable).values)
            co2_values.append(emission_threshold)
            print(f"NPC: {npc_values[-1] / 1000} kUSD, CO₂: {co2_values[-1] / 1000} tonCO₂")

            # Remove CO₂ constraint for the next iteration
            self.model.remove_constraints(f"co2_threshold_{i}")

        print("Pareto front generation completed.")

        # Return NPC and CO₂ values as a list of tuples for Pareto front plotting
        return list(zip(co2_values, npc_values)), solutions
    
    def get_settings(self, setting_name: str, advanced: bool = False):
        settings = self.settings.advanced_settings if advanced else self.settings.project_settings
        return getattr(settings, setting_name)
    
    def get_solution_variable(self, variable_name: str) -> xr.DataArray:
        if self.solution is None:
            raise ValueError("Model has not been solved yet.")
        variable = self.solution.get(variable_name)
        if variable is None:
            raise ValueError(f"Variable '{variable_name}' not found in the solution.")
        return variable