"""Resource lifecycle classifications shared by deletion policy and owned storage."""

# Internal run containers have no independent CRUD lifecycle and do not block parent deletion.
AUXILIARY_TASK_TYPES = ("test_report_generate", "test_order_graph")
