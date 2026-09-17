VAR_GLOBAL
	(* 6061 Modes of operation display；蓝塔三轴固定输入地址。 *)
	siElModeDisplay AT %IB22 : SINT;
	siAzModeDisplay AT %IB42 : SINT;
	siTiModeDisplay AT %IB62 : SINT;
	(* 6081 Profile velocity；蓝塔三轴固定输出地址。 *)
	udiElProfileVelocity AT %QD6 : UDINT;
	udiAzProfileVelocity AT %QD12 : UDINT;
	udiTiProfileVelocity AT %QD18 : UDINT;

	(* 可选扩展诊断，供可视化或后续新增IR使用。 *)
	stElPpCspStatus : ST_AxisStatus;
	stAzPpCspStatus : ST_AxisStatus;
	stTiPpCspStatus : ST_AxisStatus;
END_VAR
