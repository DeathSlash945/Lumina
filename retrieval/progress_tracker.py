import logging
from retrieval.schemas import MasterLearningPath, CompletionStatus

log = logging.getLogger("lumina.progress")

class ProgressTracker:
    @staticmethod
    def update_resource_status(
        path: MasterLearningPath, 
        step_idx: int, 
        resource_idx: int, 
        new_status: CompletionStatus
    ) -> MasterLearningPath:
        if 0 <= step_idx < len(path.steps):
            node = path.steps[step_idx]
            if 0 <= resource_idx < len(node.resources):
                node.resources[resource_idx].status = new_status
                
                # Auto-update node status based on resource states
                statuses = [r.status for r in node.resources]
                if all(s == CompletionStatus.COMPLETED for s in statuses):
                    node.status = CompletionStatus.COMPLETED
                elif any(s in [CompletionStatus.IN_PROGRESS, CompletionStatus.COMPLETED] for s in statuses):
                    node.status = CompletionStatus.IN_PROGRESS
                else:
                    node.status = CompletionStatus.NOT_STARTED
        return path

#to be applied too
    @staticmethod
    def update_step_status(
        path: MasterLearningPath, 
        step_idx: int, 
        new_status: CompletionStatus
    ) -> MasterLearningPath:
        if 0 <= step_idx < len(path.steps):
            node = path.steps[step_idx]
            node.status = new_status
            for resource in node.resources:
                resource.status = new_status
        return path