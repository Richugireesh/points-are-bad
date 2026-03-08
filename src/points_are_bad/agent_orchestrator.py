import yaml

class AgentSystem:
    def __init__(self, config_path="agent.yaml"):
        # Load the configuration from agent.yaml
        with open(config_path, 'r') as file:
            self.config = yaml.safe_load(file)
            
        self.orchestrator = self.config.get("orchestrator", {})
        self.specialists = {agent['name']: agent for agent in self.config.get("specialists", [])}
        
    def initialize_team(self):
        print(f"Initializing {self.config.get('name')} Team...")
        print(f"--> Booting Orchestrator: {self.orchestrator.get('name')} [{self.orchestrator.get('model')}]")
        for name, spec in self.specialists.items():
            print(f"--> Booting Specialist: {name} [{spec.get('model')}] with tools: {spec.get('tools')}")
            
    def route_request(self, user_prompt):
        print(f"\n[LeadDeveloper] Analyzing user request: '{user_prompt}'")
        
        # Extremely simplified routing mockup:
        if "api" in user_prompt.lower() or "fetch" in user_prompt.lower() or "openf1" in user_prompt.lower():
            target = "APIDataIntegrator"
        elif "review" in user_prompt.lower() or "quality" in user_prompt.lower() or "bug" in user_prompt.lower() or "best practice" in user_prompt.lower():
            target = "CodeReviewer"
        elif "test" in user_prompt.lower() or "pytest" in user_prompt.lower() or "unit" in user_prompt.lower():
            target = "Tester"
        elif "architect" in user_prompt.lower() or "structure" in user_prompt.lower() or "flow" in user_prompt.lower() or "scalable" in user_prompt.lower():
            target = "Architect"
        elif "point" in user_prompt.lower() or "alias" in user_prompt.lower() or "score" in user_prompt.lower():
            target = "GameLogicCoder"
        else:
            target = "GameLogicCoder" # Fallback
            
        self._delegate_to_specialist(target, user_prompt)
        
    def _delegate_to_specialist(self, agent_name, context):
        specialist = self.specialists.get(agent_name)
        if not specialist:
            print(f"[ERROR] Sub-agent {agent_name} not found.")
            return
            
        print(f"[{self.orchestrator.get('name')}] Routing task to -> {agent_name}")
        print(f"[{agent_name}] Executing task with tools: {specialist.get('tools')}...")
        # Here you would actually invoke the LLM with the specialist's system instructions and available tools
        print(f"[{agent_name}] Task complete. Returning artifacts to Orchestrator.")

def main():
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "agent.yaml"
    
    try:
        # Initialize the agent system and handle message-routing
        team = AgentSystem(config_path)
        team.initialize_team()
        
        # Mocking user interaction:
        team.route_request("Update the OpenF1 endpoints to fetch practice session results instead of race results.")
        team.route_request("Add a new nickname 'smooth operator' to map to Carlos Sainz in the point logic.")
        team.route_request("Can you review the calculate_str_equality function and check if it follows best practices?")
        team.route_request("Write unit tests using pytest for the calculate_player_points_for_race logic.")
        team.route_request("We need to structure the codebase better. Please architect a new module flow.")
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        print("Please run this command from the directory containing agent.yaml or specify the path.")

if __name__ == "__main__":
    main()
