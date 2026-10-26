package fixture;
import org.springframework.transaction.annotation.Transactional;
public class Propagation {
    static class Nested {
        @Transactional(propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW)
        static void work() {}
    }
    public void run() { Nested.work(); }
}
