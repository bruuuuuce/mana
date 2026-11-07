package investigation;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfig {
    @Bean public DataSourceTransactionManager tx() { return new DataSourceTransactionManager(); }
}

@Service
class OrderService {
    @Autowired InventoryService inventory;
    @Autowired LedgerService ledger;
    @Autowired DynamicSqlService dynamic;

    @Transactional public void process() {
        inventory.join();
        ledger.independent();
        inventory.nested();
        this.selfRequiresNew();
        dynamic.runDynamic();
    }

    @Transactional public void newBoundary() { ledger.independent(); }
    @Transactional public void nestedBoundary() { inventory.nested(); }
    @Transactional public void accountThenLedger() { inventory.lockAccount(); ledger.lockLedger(); }
    @Transactional public void ledgerThenAccount() { ledger.lockLedger(); inventory.lockAccount(); }
    @Transactional public void selfInvocation() { this.selfRequiresNew(); }
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void selfRequiresNew() { inventory.lockAccount(); }
}

@Service
class InventoryService {
    @Autowired JdbcTemplate jdbc;
    @Transactional public void join() { jdbc.update("UPDATE inventory SET quantity = 1"); }
    @Transactional(propagation = Propagation.NESTED)
    public void nested() { jdbc.execute("SELECT * FROM inventory FOR UPDATE"); }
    public void lockAccount() { jdbc.execute("SELECT * FROM accounts FOR UPDATE"); }
}

@Service
class LedgerService {
    @Autowired JdbcTemplate jdbc;
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void independent() { jdbc.update("UPDATE ledger SET amount = 1"); }
    public void lockLedger() { jdbc.execute("SELECT * FROM ledger FOR UPDATE"); }
}

@Service
class DynamicSqlService {
    @Autowired JdbcTemplate jdbc;
    public void runDynamic() { jdbc.execute(sqlForCurrentTenant()); }
    private String sqlForCurrentTenant() { return "SELECT * FROM accounts"; }
}
